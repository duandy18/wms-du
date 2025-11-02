import pytest

pytestmark = pytest.mark.grp_snapshot

import pytest
from sqlalchemy import text

from tests.services._helpers import ensure_store, uniq_ref

pytestmark = pytest.mark.asyncio


async def test_reserved_adjust_idempotent(session):
    from app.services.channel_inventory_service import ChannelInventoryService
    from app.services.stock_service import StockService

    svc = ChannelInventoryService()
    item, loc = 3401, 1
    store = await ensure_store(session)
    await StockService().adjust(
        session=session, item_id=item, location_id=loc, delta=15, reason="INBOUND"
    )

    ref = uniq_ref("RSV")
    r1 = await svc.adjust_reserved(session=session, store_id=store, item_id=item, delta=-9, ref=ref)
    r2 = await svc.adjust_reserved(session=session, store_id=store, item_id=item, delta=-9, ref=ref)
    assert r1.get("idempotent") is False
    assert r2.get("idempotent") is True

    # 预占与可见量关系（可选校验：visible 不小于 0）
    v = await session.execute(
        text("SELECT COALESCE(visible,0) FROM channel_inventory WHERE store_id=:s AND item_id=:i"),
        {"s": store, "i": item},
    )
    assert int(v.scalar() or 0) >= 0
