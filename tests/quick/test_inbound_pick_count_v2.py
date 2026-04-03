from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.stock.services.lots import ensure_internal_lot_singleton
from app.wms.stock.services.stock_service import StockService

UTC = timezone.utc


async def _ensure_internal_lot(session: AsyncSession, *, item_id: int, wh: int, ref: str) -> int:
    """
    Lot-World 终态：lot_id 是库存唯一身份。
    “非批次商品的 NULL 槽位”由 INTERNAL 单例 lot 承载（lot_code=NULL，(wh,item) 只有一个）。
    """
    _ = ref
    return await ensure_internal_lot_singleton(
        session,
        item_id=int(item_id),
        warehouse_id=int(wh),
        source_receipt_id=None,
        source_line_no=None,
    )


async def _qty(session: AsyncSession, item_id: int, wh: int, lot_id: int) -> int:
    r = await session.execute(
        text(
            """
            SELECT COALESCE(qty, 0)
              FROM stocks_lot
             WHERE item_id=:i
               AND warehouse_id=:w
               AND lot_id=:lot
             LIMIT 1
            """
        ),
        {"i": item_id, "w": wh, "lot": lot_id},
    )
    return int(r.scalar_one_or_none() or 0)


@pytest.mark.asyncio
async def test_receive_then_pick_then_count(session: AsyncSession):
    svc = StockService()
    item_id = 1
    wh = 1

    # 本用例要测 NONE/internal-lot 语义：局部把该 item 改回 NONE
    await session.execute(
        text("UPDATE items SET expiry_policy='NONE'::expiry_policy WHERE id=:i"),
        {"i": int(item_id)},
    )
    await session.commit()

    lot_id = await _ensure_internal_lot(session, item_id=item_id, wh=wh, ref="UT-IPC-INTERNAL-RECEIPT-1")
    batch_code: str | None = None

    await svc.adjust_lot(
        session=session,
        item_id=item_id,
        warehouse_id=wh,
        lot_id=int(lot_id),
        delta=2,
        reason=MovementType.INBOUND,
        ref="Q-IPC-1",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=batch_code,
    )
    q1 = await _qty(session, item_id, wh, lot_id)
    assert q1 >= 2

    await svc.adjust_lot(
        session=session,
        item_id=item_id,
        warehouse_id=wh,
        lot_id=int(lot_id),
        delta=-1,
        reason=MovementType.OUTBOUND,
        ref="Q-IPC-2",
        ref_line=1,
        occurred_at=datetime.now(UTC),
        batch_code=batch_code,
    )
    q2 = await _qty(session, item_id, wh, lot_id)
    assert q2 == q1 - 1

    remain = await _qty(session, item_id, wh, lot_id)
    delta = 1 - remain
    if delta != 0:
        await svc.adjust_lot(
            session=session,
            item_id=item_id,
            warehouse_id=wh,
            lot_id=int(lot_id),
            delta=delta,
            reason=MovementType.COUNT,
            ref="Q-IPC-3",
            ref_line=1,
            occurred_at=datetime.now(UTC),
            batch_code=batch_code,
        )
    q3 = await _qty(session, item_id, wh, lot_id)
    assert q3 == 1
