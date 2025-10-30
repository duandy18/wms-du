import pytest

pytestmark = pytest.mark.grp_snapshot

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _exec(engine, sql, params=None, one=True):
    async with engine.begin() as conn:
        rows = await conn.execute(text(sql), params or {})
        return rows.mappings().first() if one else rows.mappings().all()


async def _sum(engine, sql):
    async with engine.begin() as conn:
        row = await conn.execute(text(sql))
        return row.scalar() or 0


async def _seed_inbound(session, item, loc, qty, ref="DBV-SEED"):
    from app.services.stock_service import StockService

    svc = StockService()
    await svc.adjust(
        session=session, item_id=item, location_id=loc, delta=qty, reason="INBOUND", ref=ref
    )


async def test_v_available_and_three_books_with_snapshot(session):
    """
    口径金三角：
      - v_available: on_hand = SUM(stocks.qty), reserved = ACTIVE 预留
      - v_three_books: sum_stocks == sum_ledger ≈ sum_snapshot_on_hand
      - snapshot_today(): 幂等 UPSERT
    """
    engine = session.bind
    item, loc = 81001, 1

    # 1) 造数：入库 10，预留 7（ACTIVE）
    await _seed_inbound(session, item, loc, 10)
    await session.execute(
        text(
            "INSERT INTO reservations(item_id,location_id,qty,ref,status) VALUES (:i,:l,7,'DBV-RES','ACTIVE') ON CONFLICT DO NOTHING"
        ),
        {"i": item, "l": loc},
    )
    await session.commit()

    # 2) v_available 口径：10-7=3
    row = await _exec(
        engine,
        "SELECT on_hand,reserved,available FROM v_available WHERE item_id=:i AND location_id=:l",
        {"i": item, "l": loc},
    )
    assert row and row["on_hand"] == 10 and row["reserved"] == 7 and row["available"] == 3

    # 3) 跑日结（幂等两次）
    await session.execute(text("CALL snapshot_today()"))
    await session.execute(text("CALL snapshot_today()"))
    await session.commit()

    # 4) 三账（stocks vs ledger vs snapshot）
    t = await _exec(engine, "SELECT * FROM v_three_books")
    assert int(t["sum_stocks"]) == int(t["sum_ledger"])  # 账上现存 == 台账累计

    # 最新快照 on_hand ≥ available，且与 sum_stocks 接近（允许仅今日未跑时有微差，这里已经跑过）
    assert int(t["sum_snapshot_on_hand"]) == int(t["sum_stocks"])


async def test_snapshot_totals_specific_day(session):
    """指定日期 totals(day) 能定位到最近运行日或空结果不报错"""
    from app.services.snapshot_service import SnapshotService

    await session.execute(text("CALL snapshot_today()"))
    svc = SnapshotService()
    res = await svc.totals(session)  # 最近一天
    assert {"snapshot_date", "sum_on_hand", "sum_available"}.issubset(res.keys())
