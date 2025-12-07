# tests/services/test_fefo_allocator.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code, seed_batch_slot

from app.models.enums import MovementType
from app.services.fefo_allocator import FefoAllocator
from app.services.stock_service import StockService

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_fefo_ship_uses_earliest_expiry_first(session: AsyncSession):
    wh, loc, item = 1, 1, 3001
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    # NEAR(2天,3) + FAR(30天,5)
    today = datetime.now(UTC).date()
    await seed_batch_slot(session, item=item, loc=loc, code="NEAR", qty=3, days=2)
    await seed_batch_slot(session, item=item, loc=loc, code="FAR", qty=5, days=30)
    await session.commit()

    alloc = FefoAllocator(stock=StockService())
    ref = f"SO-{int(datetime.now(UTC).timestamp())}"
    occurred_at = datetime.now(UTC)

    async with session.begin():
        await alloc.ship(
            session=session,
            item_id=item,
            location_id=loc,
            qty=4,
            ref=ref,
            reason=MovementType.SHIPMENT,
            occurred_at=occurred_at,
            allow_expired=False,
        )

    # NEAR 3 -> 0；FAR 5 -> 4
    near = await qty_by_code(session, item=item, loc=loc, code="NEAR")
    far = await qty_by_code(session, item=item, loc=loc, code="FAR")
    assert near == 0 and far == 4
