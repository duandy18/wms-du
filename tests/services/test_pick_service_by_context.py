# tests/services/test_pick_service_by_context.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot

from app.schemas.outbound import OutboundLine, OutboundMode
from app.services.outbound_service import OutboundService

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_pick_by_context_selects_line_and_updates_status(session: AsyncSession):
    wh, loc, item, code = 1, 1, 7661, "PICK-7661"
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await seed_batch_slot(session, item=item, loc=loc, code=code, qty=3, days=365)
    await session.commit()

    ref = f"SO-PICK-{int(datetime.now(UTC).timestamp())}"
    async with session.begin():
        res = await OutboundService.commit(
            session,
            platform="pdd",
            shop_id=None,
            ref=ref,
            occurred_at=datetime.now(UTC),
            lines=[OutboundLine(item_id=item, location_id=loc, qty=1)],
            mode=OutboundMode.FEFO.value,
            allow_expired=False,
            warehouse_id=wh,
        )
    assert res["ok"] is True
