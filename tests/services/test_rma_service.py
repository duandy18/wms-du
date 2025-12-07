# tests/services/test_rma_service.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code

from app.services.inbound_service import InboundService
from app.services.putaway_service import PutawayService

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_rma_return_good_and_defect(session: AsyncSession):
    wh, loc_good, loc_def, item, code = 1, 1, 2, 7721, "RMA-7721"
    await ensure_wh_loc_item(session, wh=wh, loc=loc_good, item=item, code="GOOD", name="GOOD")
    await ensure_wh_loc_item(session, wh=wh, loc=loc_def, item=item, code="DEFECT", name="DEFECT")
    await session.commit()

    # GOOD 收 5
    async with session.begin():
        _ = await InboundService().receive(
            session=session,
            item_id=item,
            location_id=loc_good,
            qty=5,
            ref="IN-RMA",
            occurred_at=datetime.now(UTC),
            batch_code=code,
            expiry_date=(date.today() + timedelta(days=365)),
        )
    assert await qty_by_code(session, item=item, loc=loc_good, code=code) == 5
    await session.commit()  # 读后提交，再 begin

    # 搬 2 到 DEFECT
    async with session.begin():
        _ = await PutawayService().putaway(
            session=session,
            item_id=item,
            from_location_id=loc_good,
            to_location_id=loc_def,
            qty=2,
            ref="RMA-RET",
            batch_code=code,
            left_ref_line=1,
        )

    assert await qty_by_code(session, item=item, loc=loc_good, code=code) == 3
    assert await qty_by_code(session, item=item, loc=loc_def, code=code) == 2
