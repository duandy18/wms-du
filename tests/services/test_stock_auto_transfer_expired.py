# tests/services/test_stock_auto_transfer_expired.py
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
async def test_auto_transfer_expired(session: AsyncSession):
    """
    验证：默认不发货过期批次。
    - EXP(2, 已过期) + N(2, 未过期)
    - allow_expired=False，出库 2 → 仅从 N 扣 2，EXP 不动
    """
    wh, loc, item = 1, 1, 7731
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)

    today = date.today()
    await seed_batch_slot(session, item=item, loc=loc, code="EXP", qty=2, days=-1)  # 已过期
    await seed_batch_slot(session, item=item, loc=loc, code="N", qty=2, days=7)  # 未来
    await session.commit()  # 造数完成，关闭隐式事务

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

    # 过期未扣、未过期扣完
    assert await qty_by_code(session, item=item, loc=loc, code="EXP") == 2
    assert await qty_by_code(session, item=item, loc=loc, code="N") == 0
