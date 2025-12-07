# tests/services/test_reconcile_service.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot, sum_on_hand

from app.services.reconcile_service import ReconcileService

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_reconcile_up_and_down(session: AsyncSession):
    """
    造 A=6, B=4 → 总量 10；
    reconcile 到 15（+5），再到 11（-4）
    """
    wh, loc, item = 1, 1, 7007
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await seed_batch_slot(session, item=item, loc=loc, code="A", qty=6, days=365)
    await seed_batch_slot(session, item=item, loc=loc, code="B", qty=4, days=365)
    await session.commit()

    # 读 → 提交 → begin
    assert await sum_on_hand(session, item=item, loc=loc) == 10
    await session.commit()

    svc = ReconcileService()
    async with session.begin():
        r1 = await svc.reconcile(
            session=session, item_id=item, location_id=loc, actual_qty=15, ref="CC-1"
        )
    assert int(r1.get("delta", 0)) == 5

    # 读 → 提交 → begin
    assert await sum_on_hand(session, item=item, loc=loc) == 15
    await session.commit()
    async with session.begin():
        r2 = await svc.reconcile(
            session=session, item_id=item, location_id=loc, actual_qty=11, ref="CC-2"
        )
    assert int(r2.get("delta", 0)) == -4
    assert await sum_on_hand(session, item=item, loc=loc) == 11
