# tests/services/test_inventory_ops.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code, seed_batch_slot

from app.services.inbound_service import InboundService
from app.services.putaway_service import PutawayService

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_transfer_basic(session: AsyncSession):
    wh, src, dst, item, code = 1, 900, 1, 7201, "MV-7201"
    await ensure_wh_loc_item(session, wh=wh, loc=src, item=item, code="SRC-900")
    await ensure_wh_loc_item(session, wh=wh, loc=dst, item=item, code="DST-001")

    # 源位先收货 5
    inb = InboundService()
    await session.commit()
    async with session.begin():
        await inb.receive(
            session=session,
            item_id=item,
            location_id=src,
            qty=5,
            ref="IN-MV-1",
            occurred_at=datetime.now(UTC),
            batch_code=code,
            expiry_date=(date.today() + timedelta(days=365)),
        )
    assert await qty_by_code(session, item=item, loc=src, code=code) == 5

    # 搬运 3 到目标
    pa = PutawayService()
    await session.commit()
    async with session.begin():
        res = await pa.putaway(
            session=session,
            item_id=item,
            from_location_id=src,
            to_location_id=dst,
            qty=3,
            ref="PA-MV-1",
            batch_code=code,
            left_ref_line=1,
        )
    assert res["moved"] == 3
    assert await qty_by_code(session, item=item, loc=src, code=code) == 2
    assert await qty_by_code(session, item=item, loc=dst, code=code) == 3


@pytest.mark.asyncio
async def test_transfer_idempotent(session: AsyncSession):
    wh, src, dst, item, code = 1, 901, 2, 7202, "MV-7202"
    await ensure_wh_loc_item(session, wh=wh, loc=src, item=item, code="SRC-901")
    await ensure_wh_loc_item(session, wh=wh, loc=dst, item=item, code="DST-002")

    inb = InboundService()
    await session.commit()
    async with session.begin():
        await inb.receive(
            session=session,
            item_id=item,
            location_id=src,
            qty=4,
            ref="IN-MV-2",
            occurred_at=datetime.now(UTC),
            batch_code=code,
            expiry_date=(date.today() + timedelta(days=365)),
        )
    assert await qty_by_code(session, item=item, loc=src, code=code) == 4

    pa = PutawayService()
    await session.commit()
    # 第一次
    async with session.begin():
        _ = await pa.putaway(
            session=session,
            item_id=item,
            from_location_id=src,
            to_location_id=dst,
            qty=2,
            ref="PA-MV-2",
            batch_code=code,
            left_ref_line=1,
        )
    # 第二次（同 ref/line → 幂等）
    await session.commit()
    async with session.begin():
        _ = await pa.putaway(
            session=session,
            item_id=item,
            from_location_id=src,
            to_location_id=dst,
            qty=2,
            ref="PA-MV-2",
            batch_code=code,
            left_ref_line=1,
        )

    assert await qty_by_code(session, item=item, loc=src, code=code) == 2
    assert await qty_by_code(session, item=item, loc=dst, code=code) == 2
