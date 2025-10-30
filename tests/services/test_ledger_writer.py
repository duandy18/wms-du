import pytest

pytestmark = pytest.mark.grp_core

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def _sum_inv(session, item):
    r = await session.execute(
        text("SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i"), {"i": item}
    )
    return int(r.scalar() or 0)


async def _sum_ledger(session, item):
    r = await session.execute(
        text("SELECT COALESCE(SUM(delta),0) FROM stock_ledger WHERE item_id=:i"), {"i": item}
    )
    return int(r.scalar() or 0)


async def test_ledger_conservation(session):
    from app.services.stock_service import StockService

    item = 3301
    s = StockService()
    await s.adjust(session=session, item_id=item, location_id=1, delta=10, reason="INBOUND")
    await s.adjust(session=session, item_id=item, location_id=1, delta=-3, reason="OUTBOUND")
    await s.adjust(session=session, item_id=item, location_id=1, delta=7, reason="ADJUST")

    assert await _sum_inv(session, item) == await _sum_ledger(session, item)
