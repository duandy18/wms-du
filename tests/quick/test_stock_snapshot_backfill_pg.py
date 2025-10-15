# tests/quick/test_stock_snapshot_backfill_pg.py
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_engine
from app.jobs.snapshot import run_once
from app.models.item import Item
from app.models.location import Location

pytestmark = pytest.mark.asyncio


async def _qty_col(session: AsyncSession) -> str:
    """检测 stock_snapshots 的数量列：优先 qty，其次 qty_on_hand。"""
    rows = await session.execute(
        text(
            """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='stock_snapshots'
    """
        )
    )
    names = {r[0] for r in rows.fetchall()}
    if "qty" in names:
        return "qty"
    if "qty_on_hand" in names:
        return "qty_on_hand"
    raise RuntimeError("stock_snapshots has neither 'qty' nor 'qty_on_hand' column")


async def _ins_item(session: AsyncSession, sku: str) -> int:
    await session.execute(
        text("INSERT INTO items (sku,name) VALUES (:s,:n) ON CONFLICT DO NOTHING"),
        {"s": sku, "n": sku},
    )
    iid = await session.scalar(select(Item.id).where(Item.sku == sku))
    return int(iid)


async def _ins_location(session: AsyncSession, loc_id: int, name: str) -> int:
    exists = await session.scalar(select(Location.id).where(Location.id == loc_id))
    if exists is None:
        await session.execute(
            text(
                "INSERT INTO locations (id,name,warehouse_id) VALUES (:i,:n,1) ON CONFLICT (id) DO NOTHING"
            ),
            {"i": loc_id, "n": name},
        )
    return loc_id


async def _get_stock_id(session: AsyncSession, item_id: int, loc_id: int) -> int:
    return int(
        (
            await session.execute(
                text("SELECT id FROM stocks WHERE item_id=:i AND location_id=:l"),
                {"i": item_id, "l": loc_id},
            )
        ).scalar_one()
    )


async def test_backfill(session: AsyncSession):
    # 造维度
    item_id = await _ins_item(session, "SNAP-2")
    loc_id = await _ins_location(session, 12, "L12")

    # 确保 stocks 行存在
    await session.execute(
        text(
            "INSERT INTO stocks (item_id, location_id, qty) "
            "VALUES (:i,:l,0) ON CONFLICT (item_id,location_id) DO NOTHING"
        ),
        {"i": item_id, "l": loc_id},
    )

    # 造 T-1 与 T 窗口内的两笔台账：+2（T-1 10:00），+5（T 10:00）
    dayT = datetime(2025, 10, 10, tzinfo=UTC)
    dayT_1 = datetime(2025, 10, 9, tzinfo=UTC)

    sid = await _get_stock_id(session, item_id, loc_id)
    await session.execute(
        text(
            "INSERT INTO stock_ledger (stock_id, reason, after_qty, delta, occurred_at, ref, ref_line) "
            "VALUES (:sid,'TEST',0, 2, :t1, 'R1',1), (:sid,'TEST',0, 5, :t2, 'R2',1) "
            "ON CONFLICT DO NOTHING"
        ),
        {"sid": sid, "t1": dayT_1.replace(hour=10), "t2": dayT.replace(hour=10)},
    )
    await session.commit()

    # 先跑 T（cut=T 00:00）
    await run_once(async_engine, grain="day", at=dayT, prev=None)

    # 再回灌 T-1（cut=T-1 00:00），不应污染 T 的结果
    await run_once(async_engine, grain="day", at=dayT_1, prev=None)

    qcol = await _qty_col(session)

    qT_1 = (
        await session.execute(
            text(
                f"SELECT {qcol} FROM stock_snapshots WHERE snapshot_date=:c AND item_id=:i AND location_id=:l"
            ),
            {"c": dayT_1.date(), "i": item_id, "l": loc_id},
        )
    ).scalar_one()

    qT = (
        await session.execute(
            text(
                f"SELECT {qcol} FROM stock_snapshots WHERE snapshot_date=:c AND item_id=:i AND location_id=:l"
            ),
            {"c": dayT.date(), "i": item_id, "l": loc_id},
        )
    ).scalar_one()

    assert float(qT_1) == 2.0
    assert float(qT) == 5.0
