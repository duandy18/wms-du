# tests/services/test_fefo_rank_view_consistency.py
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, qty_by_code, seed_batch_slot

from app.schemas.outbound import OutboundLine, OutboundMode
from app.services.outbound_service import OutboundService

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_fefo_rank_matches_outbound_choice(session: AsyncSession):
    """
    场景：同库位三个批次 (E1/E2/E3) 各 2 件，E1 > E2 > E3 到期更近。
    期望：按 FEFO 出 1 件时，应优先扣减 E1。
    """
    wh, loc, item = 1, 1, 7101
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)

    # 按到期先后造数：E1(2天)、E2(5天)、E3(30天)，每批 qty=2
    await seed_batch_slot(session, item=item, loc=loc, code="E1", qty=2, days=2)
    await seed_batch_slot(session, item=item, loc=loc, code="E2", qty=2, days=5)
    await seed_batch_slot(session, item=item, loc=loc, code="E3", qty=2, days=30)
    await session.commit()

    # 出库 1（FEFO、禁止使用过期）
    ref = f"SO-FEFO-{int(datetime.now(UTC).timestamp())}"
    occurred_at = datetime.now(UTC)
    await session.commit()
    async with session.begin():
        _ = await OutboundService.commit(
            session,
            platform="pdd",
            shop_id=None,
            ref=ref,
            occurred_at=occurred_at,
            lines=[OutboundLine(item_id=item, location_id=loc, qty=1)],
            mode=OutboundMode.FEFO.value,
            allow_expired=False,
            warehouse_id=wh,
        )

    # 断言：E1 应从 2 → 1，其余不变
    assert await qty_by_code(session, item=item, loc=loc, code="E1") == 1
    assert await qty_by_code(session, item=item, loc=loc, code="E2") == 2
    assert await qty_by_code(session, item=item, loc=loc, code="E3") == 2
