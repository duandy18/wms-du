from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.stock.services.lots import ensure_internal_lot_singleton
from app.wms.stock.services.stock_adjust import adjust_lot_impl

UTC = timezone.utc


async def _ensure_wh(session: AsyncSession, name: str) -> int:
    row = await session.execute(text("SELECT id FROM warehouses WHERE name=:n LIMIT 1"), {"n": name})
    wid = row.scalar_one_or_none()
    if wid is not None:
        return int(wid)
    ins = await session.execute(
        text("INSERT INTO warehouses(name) VALUES(:n) ON CONFLICT(name) DO NOTHING RETURNING id"),
        {"n": name},
    )
    wid2 = ins.scalar_one_or_none()
    if wid2 is not None:
        return int(wid2)
    row2 = await session.execute(text("SELECT id FROM warehouses WHERE name=:n LIMIT 1"), {"n": name})
    return int(row2.scalar_one())


async def _qty(session: AsyncSession, item_id: int, wh: int, code: str | None) -> int:
    if code is None:
        row = await session.execute(
            text(
                """
                SELECT COALESCE(qty, 0)
                  FROM stocks_lot
                 WHERE item_id=:i
                   AND warehouse_id=:w
                 LIMIT 1
                """
            ),
            {"i": item_id, "w": wh},
        )
        return int(row.scalar_one_or_none() or 0)

    row = await session.execute(
        text(
            """
            SELECT COALESCE(sl.qty, 0)
              FROM stocks_lot sl
              JOIN lots l ON l.id = sl.lot_id
             WHERE sl.item_id=:i
               AND sl.warehouse_id=:w
               AND l.lot_code = :c
             LIMIT 1
            """
        ),
        {"i": item_id, "w": wh, "c": str(code)},
    )
    return int(row.scalar_one_or_none() or 0)


async def _ensure_internal_lot(session: AsyncSession, *, item_id: int, wh: int) -> int:
    lot_id = await ensure_internal_lot_singleton(
        session,
        item_id=int(item_id),
        warehouse_id=int(wh),
        source_receipt_id=None,
        source_line_no=None,
    )
    return int(lot_id)


async def _write_delta(
    session: AsyncSession,
    *,
    item_id: int,
    wh: int,
    lot_id: int,
    delta: int,
    reason: str,
    ref: str,
    ref_line: int,
) -> None:
    await adjust_lot_impl(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(wh),
        lot_id=int(lot_id),
        delta=int(delta),
        reason=str(reason),
        ref=str(ref),
        ref_line=int(ref_line),
        occurred_at=datetime.now(UTC),
        meta=None,
        lot_code=None,
        production_date=None,
        expiry_date=None,
        trace_id=None,
        utc_now=lambda: datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_inbound_receive_and_reclassify_integrity(session: AsyncSession):
    item_id = 1
    wh_returns = await _ensure_wh(session, "RETURNS")
    wh_main = await _ensure_wh(session, "MAIN")

    # 本用例要测 NONE/internal-lot 语义：局部把该 item 改回 NONE
    await session.execute(
        text("UPDATE items SET expiry_policy='NONE'::expiry_policy WHERE id=:i"),
        {"i": int(item_id)},
    )
    await session.commit()

    batch_code: str | None = None

    lot_returns = await _ensure_internal_lot(session, item_id=item_id, wh=wh_returns)
    lot_main = await _ensure_internal_lot(session, item_id=item_id, wh=wh_main)

    await _write_delta(
        session,
        item_id=item_id,
        wh=wh_returns,
        lot_id=lot_returns,
        delta=+2,
        reason=MovementType.INBOUND,
        ref="PO-R1",
        ref_line=1,
    )
    r0 = await _qty(session, item_id, wh_returns, batch_code)
    assert r0 >= 2

    await _write_delta(
        session,
        item_id=item_id,
        wh=wh_returns,
        lot_id=lot_returns,
        delta=-1,
        reason="RETURN_RECLASSIFY",
        ref="X-MOVE-1",
        ref_line=1,
    )
    await _write_delta(
        session,
        item_id=item_id,
        wh=wh_main,
        lot_id=lot_main,
        delta=+1,
        reason="RETURN_RECLASSIFY",
        ref="X-MOVE-1",
        ref_line=2,
    )

    r1 = await _qty(session, item_id, wh_returns, batch_code)
    m1 = await _qty(session, item_id, wh_main, batch_code)
    assert r1 == r0 - 1
    assert m1 >= 1
    assert (r1 + m1) == (r0 + (m1 - 1))
