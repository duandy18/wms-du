from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot

from app.services.channel_inventory_service import ChannelInventoryService
from app.services.order_service import OrderService

UTC = timezone.utc
pytestmark = pytest.mark.contract


@pytest.mark.asyncio
async def test_fefo_reserve_then_cancel(session: AsyncSession):
    """
    Phase 3.6 版合同：

    场景：
      - 仓库 1 / 库位 1 / 商品 7301，有一批次 code='RES-7301'，qty=5
      - 平台 PDD / 店铺 SHOP1：
          * 调用 OrderService.reserve 占用 2
          * 可售库存应从 available0 降到 available0-2
          * 调用 OrderService.cancel 取消该 ref
          * 可售库存应恢复为 available0
    """

    wh, loc, item, code = 1, 1, 7301, "RES-7301"

    # 1) 基线：准备仓/库位/商品 + 批次 + 库存槽位
    await ensure_wh_loc_item(session, wh=wh, loc=loc, item=item)
    await seed_batch_slot(session, item=item, loc=loc, code=code, qty=5, days=365)
    await session.commit()

    # 2) 读 baseline 可售库存（按平台/店铺/仓库）
    platform = "PDD"
    shop_id = "SHOP1"
    ref = "RES-TEST-7301"

    chan = ChannelInventoryService()
    available0 = await chan.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=wh,
        item_id=item,
    )

    # 至少有 5 件（我们刚 seed 了一批），但为了容忍已有基础数据，只要求 >=2
    assert available0 >= 2

    # 3) 调用 OrderService.reserve 占用 2 件
    r1 = await OrderService.reserve(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=ref,
        lines=[{"item_id": item, "qty": 2}],
    )
    assert r1["status"] == "OK"
    assert r1["reservation_id"] is not None
    await session.commit()

    available1 = await chan.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=wh,
        item_id=item,
    )
    assert available1 == available0 - 2

    # 4) 调用 OrderService.cancel 取消该预留
    r2 = await OrderService.cancel(
        session,
        platform=platform,
        shop_id=shop_id,
        ref=ref,
        lines=[{"item_id": item, "qty": 2}],
    )
    assert r2["status"] in ("CANCELED", "NOOP")  # 在高并发/重放场景下允许 NOOP
    await session.commit()

    available2 = await chan.get_available_for_item(
        session,
        platform=platform,
        shop_id=shop_id,
        warehouse_id=wh,
        item_id=item,
    )

    # 最终可售应回到 baseline
    assert available2 == available0
