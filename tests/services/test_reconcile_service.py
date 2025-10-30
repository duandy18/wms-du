import pytest

pytestmark = pytest.mark.grp_reverse

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _sum_stock(engine):
    async with engine.begin() as conn:
        row = await conn.execute(text("SELECT COALESCE(SUM(qty),0) FROM stocks"))
        return int(row.scalar() or 0)


async def _sum_ledger(engine):
    async with engine.begin() as conn:
        row = await conn.execute(text("SELECT COALESCE(SUM(delta),0) FROM stock_ledger"))
        return int(row.scalar() or 0)


async def _seed(session, item, loc, qty):
    from app.services.stock_service import StockService

    svc = StockService()
    await svc.adjust(
        session=session, item_id=item, location_id=loc, delta=qty, reason="INBOUND", ref="SEED"
    )


async def test_reconcile_up_and_down(session):
    from app.services.reconcile_service import ReconcileService

    engine = session.bind

    item, loc = 2301, 1
    await _seed(session, item, loc, 10)
    await session.commit()

    # 上调到 15
    res_up = await ReconcileService.reconcile_inventory(
        session=session, item_id=item, location_id=loc, counted_qty=15, ref="CC-UP-001"
    )
    await session.commit()
    # 下调到 12
    res_dn = await ReconcileService.reconcile_inventory(
        session=session, item_id=item, location_id=loc, counted_qty=12, ref="CC-DN-001"
    )
    await session.commit()

    # 三账一致性
    assert await _sum_stock(engine) == await _sum_ledger(engine)
