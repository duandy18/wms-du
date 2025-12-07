# tests/services/test_batch_service.py
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
async def test_pick_by_fefo_excludes_expired(session: AsyncSession):
    """
    目标：FEFO + 禁止过期
      - 过期批次 E(2) + 未过期批次 N(2)
      - 出库 1，allow_expired=False
      - 应选择 N，E 不应被扣
    """
    wh, loc, item = 1, 1, 7701
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)

    # 过期 & 未过期（helpers）
    today = date.today()
    await seed_batch_slot(session, item=item, loc=loc, code="E", qty=2, days=-1)  # 已过期
    await seed_batch_slot(session, item=item, loc=loc, code="N", qty=2, days=10)  # 未来
    await session.commit()  # 造数完成，关闭隐式事务

    ref = f"SO-{int(datetime.now(UTC).timestamp())}"
    occurred_at = datetime.now(UTC)

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

    # 未过期 N 应被扣 1，过期 E 保持 2
    assert await qty_by_code(session, item=item, loc=loc, code="N") == 1
    assert await qty_by_code(session, item=item, loc=loc, code="E") == 2
