# app/services/reservation_persist.py
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.reservation_service import ReservationError, ReservationService


def _now_utc_naive() -> datetime:
    return datetime.utcnow().replace(tzinfo=None)


def _ttl_minutes() -> int:
    raw = os.getenv("SOFT_RESERVE_TTL_MINUTES") or "30"
    try:
        v = int(raw)
        return v if v > 0 else 30
    except Exception:
        return 30


def _calc_expire_at(now: datetime) -> datetime:
    return now + timedelta(minutes=_ttl_minutes())


async def reserve_persist(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    lines: List[Dict[str, Any]],
    warehouse_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    预留计划持久化（PLANNED）：

    - 幂等：按 (platform, shop_id, ref) 唯一。
    - 写入 reservations（status='PLANNED'）和 reservation_lines。
    - 不写 ledger，不扣减 stocks。
    - 写入 expire_at（基于 TTL），供 TTL job 回收。
    """
    plat = platform.upper()

    # 解析店铺与仓；若未显式传入仓，解析默认仓。
    _, wh = await ReservationService.ensure_store_and_warehouse(
        session, platform=plat, shop_id=shop_id, warehouse_id=warehouse_id
    )

    # 幂等：已有同 ref 直接返回
    existed = (
        (
            await session.execute(
                text(
                    """
            SELECT id AS reservation_id, warehouse_id
              FROM reservations
             WHERE platform=:p AND shop_id=:s AND ref=:r
             LIMIT 1
        """
                ),
                {"p": plat, "s": shop_id, "r": ref},
            )
        )
        .mappings()
        .first()
    )
    if existed:
        return {
            "status": "IDEMPOTENT",
            "reservation_id": existed["reservation_id"],
            "warehouse_id": existed["warehouse_id"],
        }

    created_at = _now_utc_naive()
    updated_at = created_at
    exp = _calc_expire_at(created_at)

    # 写头
    reservation_id = (
        await session.execute(
            text(
                """
            INSERT INTO reservations (
                platform, shop_id, ref, warehouse_id,
                status, created_at, updated_at, expire_at
            )
            VALUES (:p, :s, :r, :wh, 'PLANNED', :created_at, :updated_at, :expire_at)
            RETURNING id
        """
            ),
            {
                "p": plat,
                "s": shop_id,
                "r": ref,
                "wh": wh,
                "created_at": created_at,
                "updated_at": updated_at,
                "expire_at": exp,
            },
        )
    ).scalar_one()

    # 写明细
    for idx, raw in enumerate(lines or [], start=1):
        try:
            item_id = int(raw["item_id"])
            qty = int(raw["qty"])
        except (KeyError, ValueError, TypeError) as e:
            raise ReservationError(f"INVALID_LINE_DATA[{idx}]: {e}") from e

        if item_id <= 0 or qty <= 0:
            raise ReservationError(f"INVALID_LINE_VALUE[{idx}]: item_id/qty must be positive.")

        await session.execute(
            text(
                """
                INSERT INTO reservation_lines (reservation_id, ref_line, item_id, qty)
                VALUES (:rid, :ln, :item, :qty)
                ON CONFLICT (reservation_id, ref_line) DO NOTHING
            """
            ),
            {"rid": reservation_id, "ln": idx, "item": item_id, "qty": qty},
        )

    await ReservationService.audit(
        session, ref=ref, event="PERSIST", platform=plat, shop_id=shop_id
    )

    return {
        "status": "OK",
        "reservation_id": reservation_id,
        "warehouse_id": wh,
    }
