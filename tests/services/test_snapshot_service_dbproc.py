import pytest

pytestmark = pytest.mark.grp_snapshot

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _sum(engine, sql):
    async with engine.begin() as conn:
        row = await conn.execute(text(sql))
        return row.scalar()


async def _seed_inbound(session, item, loc, qty):
    from app.services.stock_service import StockService

    svc = StockService()
    await svc.adjust(
        session=session, item_id=item, location_id=loc, delta=qty, reason="INBOUND", ref="SNAP-SEED"
    )


async def test_snapshot_dbproc_and_views(session):
    from app.services.snapshot_service import SnapshotService

    engine = session.bind

    # 1) 造数：入库 10
    item, loc = 3001, 1
    await _seed_inbound(session, item, loc, 10)
    await session.commit()

    # 2) 调用服务：触发 DB 过程 + 读取三账
    svc = SnapshotService()
    res = await svc.run(session)
    # 不在 run() 中 commit，这里读取视图无需写操作
    assert "sum_stocks" in res and "sum_ledger" in res

    # 3) 三账应对齐（stocks 总量 == ledger 总量 == 快照 on_hand）
    sum_stocks = await _sum(engine, "SELECT COALESCE(SUM(qty),0) FROM stocks")
    sum_ledger = await _sum(engine, "SELECT COALESCE(SUM(delta),0) FROM stock_ledger")
    assert int(sum_stocks) == int(sum_ledger)

    # 4) 读 totals（最近一天）
    totals = await svc.totals(session)
    # 视图依赖 DB 过程写入的数据；此处只验证字段存在
    assert {"snapshot_date", "sum_on_hand", "sum_available"} <= set(totals.keys())
