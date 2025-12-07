from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from tests.helpers.inventory import ensure_wh_loc_item
from tests.services._helpers import ensure_store, uniq_ref

pytestmark = pytest.mark.asyncio


async def test_reserved_adjust_idempotent(session):
    from app.services.channel_inventory_service import ChannelInventoryService
    from app.services.stock_service import StockService

    svc = ChannelInventoryService()
    item, warehouse_id = 3401, 1

    # 1) 确保店铺存在（内部测试店铺）
    store = await ensure_store(session)

    # 2) 确保 item / warehouse / location 等基础数据存在
    #    这一步会建 items(id=item)、warehouses(id=warehouse_id) 等，避免 FK 违反
    await ensure_wh_loc_item(session, wh=warehouse_id, loc=warehouse_id, item=item)

    # 3) 用 v2 StockService.adjust 造一批库存，确保 on_hand 足够支持后续预占 -9
    now = datetime.now(timezone.utc)
    stock_svc = StockService()

    await stock_svc.adjust(
        session=session,
        item_id=item,
        warehouse_id=warehouse_id,
        batch_code="CI-TEST-3401",
        delta=15,  # 入库 +15
        reason="INBOUND",
        ref="CI-ADJUST-1",
        ref_line=1,
        occurred_at=now,
        expiry_date=date.today() + timedelta(days=365),
    )

    # 4) 幂等调整 reserved：第一次实际扣 9，第二次视为幂等
    ref = uniq_ref("RSV")
    r1 = await svc.adjust_reserved(
        session=session,
        store_id=store,
        item_id=item,
        delta=-9,
        ref=ref,
    )
    r2 = await svc.adjust_reserved(
        session=session,
        store_id=store,
        item_id=item,
        delta=-9,
        ref=ref,
    )
    assert r1.get("idempotent") is False
    assert r2.get("idempotent") is True

    # 5) 预占与可见量关系（可选校验：visible 不小于 0）
    v = await session.execute(
        text("SELECT COALESCE(visible,0) FROM channel_inventory WHERE store_id=:s AND item_id=:i"),
        {"s": store, "i": item},
    )
    assert int(v.scalar() or 0) >= 0
