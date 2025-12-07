# tests/services/test_stock_fefo.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code, seed_batch_slot

from app.schemas.outbound import OutboundLine, OutboundMode
from app.services.outbound_service import OutboundService

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_stock_fefo_outbound(session: AsyncSession):
    """E1(2,近) + E2(2,远)，扣 3 → E1→0，E2→1"""
    wh, loc, item = 1, 1, 7741
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await seed_batch_slot(session, item=item, loc=loc, code="E1", qty=2, days=2)
    await seed_batch_slot(session, item=item, loc=loc, code="E2", qty=2, days=10)
    await session.commit()

    ref = f"SO-{int(datetime.now(UTC).timestamp())}"
    async with session.begin():
        _ = await OutboundService.commit(
            session,
            platform="pdd",
            shop_id=None,
            ref=ref,
            occurred_at=datetime.now(UTC),
            lines=[OutboundLine(item_id=item, location_id=loc, qty=3)],
            mode=OutboundMode.FEFO.value,
            allow_expired=False,
            warehouse_id=wh,
        )
    assert await qty_by_code(session, item=item, loc=loc, code="E1") == 0
    assert await qty_by_code(session, item=item, loc=loc, code="E2") == 1


@pytest.mark.asyncio
async def test_stock_fefo_disallow_expired_by_default(session: AsyncSession):
    """EXP(2,已过期) + OK(2,未过期)，扣 2 且 disallow → EXP 不变，OK→0"""
    wh, loc, item = 1, 1, 7742
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await seed_batch_slot(session, item=item, loc=loc, code="EXP", qty=2, days=-1)
    await seed_batch_slot(session, item=item, loc=loc, code="OK", qty=2, days=5)
    await session.commit()

    ref = f"SO-{int(datetime.now(UTC).timestamp())}"
    async with session.begin():
        _ = await OutboundService.commit(
            session,
            platform="pdd",
            shop_id=None,
            ref=ref,
            occurred_at=datetime.now(UTC),
            lines=[OutboundLine(item_id=item, location_id=loc, qty=2)],
            mode=OutboundMode.FEFO.value,
            allow_expired=False,
            warehouse_id=wh,
        )
    assert await qty_by_code(session, item=item, loc=loc, code="EXP") == 2
    assert await qty_by_code(session, item=item, loc=loc, code="OK") == 0
