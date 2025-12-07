# app/services/reservation_release.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger_writer import write_ledger
from app.services.reservation_service import ReservationError, ReservationService

UTC = timezone.utc


async def _allocations(session: AsyncSession, *, reservation_id: int) -> List[Tuple[int, int, int]]:
    """
    从 reservation_allocations 读取分配明细：
        -> (item_id, batch_id, qty)
    location_id 仅作为辅助维度，释放时不再参与库存键。
    """
    rows = (
        (
            await session.execute(
                text(
                    """
            SELECT item_id, batch_id, qty
              FROM reservation_allocations
             WHERE reservation_id = :rid
             FOR UPDATE
        """
                ),
                {"rid": reservation_id},
            )
        )
        .mappings()
        .all()
    )
    return [(int(r["item_id"]), int(r["batch_id"] or -1), int(r["qty"])) for r in rows]


async def release(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ref: str,
    reason: str = "canceled",  # "canceled" | "expired"
    occurred_at: Optional[datetime] = None,
) -> Dict[str, int | str]:
    """
    强释放（释放 reservation_allocations + 恢复 stocks + 写正向台账）：

    - reason="canceled": 手工取消，reservations.status -> 'RELEASED'，ledger.reason="RELEASE"
    - reason="expired": TTL 过期释放，reservations.status -> 'expired'，ledger.reason="RESERVE_EXPIRED"
    """
    reason = (reason or "canceled").lower()
    if reason not in ("canceled", "expired"):
        raise ReservationError(f"UNSUPPORTED_RELEASE_REASON: {reason}")

    plat = platform.upper()
    rid, status, wh = await ReservationService.get_reservation_head(
        session, platform=plat, shop_id=shop_id, ref=ref
    )

    # 仅 LOCKED 状态需要释放 allocations；其他状态视为幂等
    if status != "LOCKED":
        return {"status": "IDEMPOTENT", "reservation_id": rid}

    allocs = await _allocations(session, reservation_id=rid)
    now = occurred_at or datetime.now(UTC)
    ledger_reason = "RESERVE_EXPIRED" if reason == "expired" else "RELEASE"

    if not allocs:
        # 没有 allocations，直接只改头状态
        new_status = "expired" if reason == "expired" else "RELEASED"
        await session.execute(
            text(
                """
                UPDATE reservations
                   SET status=:st,
                       released_at=:now,
                       updated_at=:now
                 WHERE id=:rid
                """
            ),
            {"rid": rid, "st": new_status, "now": now},
        )
        await ReservationService.audit(
            session,
            ref=ref,
            event="RELEASE",
            platform=plat,
            shop_id=shop_id,
            extra={"empty": True, "reason": reason},
        )
        return {"status": "OK", "reservation_id": rid, "released_qty": 0}

    total_release = 0
    ref_line = 0

    for item_id, batch_id, qty in allocs:
        # 查出 batch_code（stocks 现在按 batch_code 聚合）
        row = await session.execute(
            text(
                """
                SELECT batch_code
                  FROM batches
                 WHERE id=:bid AND item_id=:item AND warehouse_id=:wh
                 LIMIT 1
                """
            ),
            {"bid": batch_id, "item": item_id, "wh": wh},
        )
        batch_code = row.scalar_one_or_none()
        if batch_code is None:
            raise ReservationError(f"BATCH_NOT_FOUND(item={item_id}, wh={wh}, batch_id={batch_id})")

        # stocks 槽位：按 (item_id, warehouse_id, batch_code) 定位
        # 先试 UPDATE，再试 INSERT
        upd = await session.execute(
            text(
                """
                UPDATE stocks
                   SET qty = qty + :q
                 WHERE item_id=:item AND warehouse_id=:wh AND batch_code=:code
             RETURNING id, qty
            """
            ),
            {"item": item_id, "wh": wh, "code": batch_code, "q": int(qty)},
        )
        row2 = upd.first()

        if not row2:
            ins = await session.execute(
                text(
                    """
                    INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
                    VALUES (:item, :wh, :code, :q)
                    ON CONFLICT (item_id, warehouse_id, batch_code)
                    DO UPDATE SET qty = stocks.qty + EXCLUDED.qty
                    RETURNING id, qty
                    """
                ),
                {"item": item_id, "wh": wh, "code": batch_code, "q": int(qty)},
            )
            row2 = ins.first()

        if not row2:
            raise ReservationError("DATABASE_CONSISTENCY_ERROR")

        _, after_qty = int(row2[0]), int(row2[1])

        # 写正向台账
        ref_line += 1
        await write_ledger(
            session,
            warehouse_id=wh,
            item_id=item_id,
            batch_code=str(batch_code),
            reason=ledger_reason,
            delta=int(qty),
            after_qty=after_qty,
            ref=ref,
            ref_line=ref_line,
            occurred_at=now,
        )

        total_release += int(qty)

    # 清 allocations
    await session.execute(
        text("DELETE FROM reservation_allocations WHERE reservation_id=:rid"), {"rid": rid}
    )

    # 更新头状态
    new_status = "expired" if reason == "expired" else "RELEASED"
    await session.execute(
        text(
            """
            UPDATE reservations
               SET status=:st,
                   released_at=:now,
                   locked_qty = GREATEST(locked_qty - :q, 0),
                   updated_at=:now
             WHERE id=:rid
        """
        ),
        {"rid": rid, "st": new_status, "now": now, "q": int(total_release)},
    )

    await ReservationService.audit(
        session,
        ref=ref,
        event="RELEASE",
        platform=plat,
        shop_id=shop_id,
        extra={"reason": reason},
    )

    return {"status": "OK", "reservation_id": rid, "released_qty": int(total_release)}
