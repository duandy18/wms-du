# app/services/stock_service_ship.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType


AdjustFn = Callable[..., Awaitable[Dict[str, Any]]]


async def ship_commit_direct_impl(
    *,
    session: AsyncSession,
    warehouse_id: int,
    platform: str,
    shop_id: str,
    ref: str,
    lines: list[dict[str, int]],
    occurred_at: Optional[datetime],
    trace_id: Optional[str],
    utc_now: Callable[[], datetime],
    adjust_fn: AdjustFn,
) -> Dict[str, Any]:
    """
    本方法保持原有行为，但 FEFO 选择更稳定（优先 expiry_date，再按 stock_id 排序）。

    Phase 3.10（本次）：
    - 引入 sub_reason（业务细分）：
      直接发货/出库链路统一标记为 ORDER_SHIP（若未来需要区分 INTERNAL_SHIP，可在调用方传 meta 覆盖）。
    """
    _ = platform
    _ = shop_id

    ts = occurred_at or utc_now()

    need_by_item: Dict[int, int] = {}
    for line in lines or []:
        item = int(line["item_id"])
        qty = int(line["qty"])
        need_by_item[item] = need_by_item.get(item, 0) + qty

    if not need_by_item:
        return {"idempotent": True, "applied": False, "ref": ref, "total_qty": 0}

    idempotent = True
    total = 0

    for item_id, want in need_by_item.items():
        existing = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(delta), 0)
                  FROM stock_ledger
                 WHERE warehouse_id=:w AND item_id=:i
                   AND ref=:ref AND delta < 0
                """
            ),
            {"w": int(warehouse_id), "i": item_id, "ref": ref},
        )
        already = int(existing.scalar() or 0)
        need = want + already
        if need <= 0:
            continue

        idempotent = False
        remain = need

        while remain > 0:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT s.batch_code, s.qty
                          FROM stocks s
                          LEFT JOIN batches b
                            ON b.item_id      = s.item_id
                           AND b.warehouse_id = s.warehouse_id
                           AND b.batch_code   = s.batch_code
                         WHERE s.item_id=:i AND s.warehouse_id=:w AND s.qty>0
                         ORDER BY b.expiry_date ASC NULLS LAST, s.id ASC
                         LIMIT 1
                        """
                    ),
                    {"i": item_id, "w": int(warehouse_id)},
                )
            ).first()

            if not row:
                raise ValueError(f"insufficient stock for item={item_id}")

            batch_code, on_hand = str(row[0]), int(row[1])
            take = min(remain, on_hand)

            await adjust_fn(
                session=session,
                item_id=item_id,
                warehouse_id=warehouse_id,
                delta=-take,
                reason=MovementType.SHIP,
                ref=ref,
                ref_line=1,
                occurred_at=ts,
                batch_code=batch_code,
                trace_id=trace_id,
                meta={
                    "sub_reason": "ORDER_SHIP",
                },
            )

            remain -= take
            total += take

    return {
        "idempotent": idempotent,
        "applied": not idempotent,
        "ref": ref,
        "total_qty": total,
    }
