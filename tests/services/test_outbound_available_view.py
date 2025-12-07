"""
Legacy: outbound 可用量视图（location 口径 + ACTIVE reservations）。

这组测试最初依赖：
  - reservations(item_id, location_id, qty, status='ACTIVE')
  - available(session, item, loc) 基于旧视图
  - OutboundService.commit(mode=FEFO, warehouse_id=wh, location_id=loc)

当前版本中：
  - 库存模型已升级为 (warehouse_id, item_id, batch_code) 粒度；
  - 可售口径由 ChannelInventoryService.get_available_for_item 提供：
      available(platform, shop_id, warehouse_id, item_id)
  - Anti-oversell 行为由 OrderService.reserve / cancel 测试覆盖：
      * tests/services/test_order_reserve_anti_oversell.py
      * tests/services/test_channel_inventory_available.py

因此，本文件标记为 legacy，不再参与当前基线。
保留文件仅为文档用途，方便日后参考旧实现对比。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy location-based outbound available test; "
        "semantics now covered by ChannelInventoryService + OrderService.reserve "
        "(see test_order_reserve_anti_oversell.py & test_channel_inventory_available.py)"
    )
)
