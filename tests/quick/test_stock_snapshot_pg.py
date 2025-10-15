# tests/quick/test_stock_snapshot_pg.py
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_engine
from app.jobs.snapshot import run_once
from app.models.item import Item
from app.models.location import Location

pytestmark = pytest.mark.asyncio


async def _ins_item_loc(session: AsyncSession, sku="SNAP-1", loc_id=11):
    iid = await session.scalar(select(Item.id).where(Item.sku == sku))
    if iid is None:
        await session.execute(
            text("INSERT INTO items (sku, name) VALUES (:s,:n)"), {"s": sku, "n": sku}
        )
        iid = await session.scalar(select(Item.id).where(Item.sku == sku))

    exists = await session.scalar(select(Location.id).where(Location.id == loc_id))
    if exists is None:
        await session.execute(
            text(
                "INSERT INTO locations (id, name, warehouse_id) VALUES (:i,:n,1) ON CONFLICT (id) DO NOTHING"
            ),
            {"i": loc_id, "n": f"LOC{loc_id}"},
        )
    return int(iid), int(loc_id)


async def _ins_stock(session: AsyncSession, item_id: int, location_id: int, qty: int):
    await session.execute(
        text(
            "INSERT INTO stocks (item_id, location_id, qty) "
            "VALUES (:i,:l,:q) "
            "ON CONFLICT (item_id,location_id) DO UPDATE SET qty=EXCLUDED.qty"
        ),
        {"i": item_id, "l": location_id, "q": qty},
    )


async def _ins_ledger(session: AsyncSession, stock_id: int, delta: int, ref: str, ts: datetime):
    await session.execute(
        text(
            "INSERT INTO stock_ledger (stock_id, reason, after_qty, delta, occurred_at, ref, ref_line) "
            "VALUES (:sid, 'TEST', 0, :d, :ts, :r, 1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"sid": stock_id, "d": delta, "ts": ts, "r": ref},
    )


async def _get_stock_id(session: AsyncSession, item_id: int, loc: int) -> int:
    return int(
        (
            await session.execute(
                text("SELECT id FROM stocks WHERE item_id=:i AND location_id=:l"),
                {"i": item_id, "l": loc},
            )
        ).scalar_one()
    )


async def _snapshot_qty_column(session: AsyncSession) -> str:
    """检测 stock_snapshots 的数量列：优先 qty，其次 qty_on_hand。"""
    cols = await session.execute(
        text(
            """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='stock_snapshots'
    """
        )
    )
    names = {r[0] for r in cols.fetchall()}
    if "qty" in names:
        return "qty"
    if "qty_on_hand" in names:
        return "qty_on_hand"
    raise RuntimeError("stock_snapshots has neither 'qty' nor 'qty_on_hand' column")


async def _get_snapshot_qty(session: AsyncSession, cut: datetime, item_id: int, loc: int) -> float:
    qcol = await _snapshot_qty_column(session)
    row = await session.execute(
        text(
            f"SELECT {qcol} FROM stock_snapshots WHERE snapshot_date=:cut AND item_id=:i AND location_id=:l"
        ),
        {"cut": cut.date(), "i": item_id, "l": loc},
    )
    r = row.scalar()
    return float(r) if r is not None else 0.0


async def test_snapshot_idempotent(session: AsyncSession):
    item_id, loc = await _ins_item_loc(session, "SNAP-1", 11)

    # 现势库存 5
    await _ins_stock(session, item_id, loc, 5)
    await session.commit()

    # 窗口内 +3 台账
    t0 = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    t1 = t0 + timedelta(minutes=10)
    sid = await _get_stock_id(session, item_id, loc)
    await _ins_ledger(session, sid, +3, "REF-A", t1)
    await session.commit()

    # 跑“当日 00:00”切片（两次，幂等）
    cut = t0.replace(hour=0, minute=0, second=0, microsecond=0)
    await run_once(async_engine, grain="day", at=cut, prev=None)
    await run_once(async_engine, grain="day", at=cut, prev=None)

    qty = await _get_snapshot_qty(session, cut, item_id, loc)
    assert qty == 3.0
