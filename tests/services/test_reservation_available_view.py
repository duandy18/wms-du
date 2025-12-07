"""
Legacy: ReservationService.available 基于旧 v_available 视图的测试。

旧实现依赖：
  - reservations(item_id, location_id, qty, status)
  - v_available / 相关视图按 (item_id, location_id) 口径统计：
      on_hand, reserved, available

当前版本中：
  - reservations/ reservation_lines 已重构为 Soft Reserve 头/行表模型：
      (platform, shop_id, warehouse_id, item_id, qty, consumed_qty, status...)
  - 可售库存的唯一口径为：
      ChannelInventoryService.get_available_for_item(platform, shop_id, warehouse_id, item_id)
  - 对“预留 → 可售减少 → 过期/释放 → 可售恢复”的行为由以下测试覆盖：
      * tests/services/test_channel_inventory_available.py
      * tests/services/test_order_reserve_anti_oversell.py

ReservationService 已不再提供 available(...) 接口，
因此本文件属于纯历史测试，不再参与当前基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy ReservationService.available test (location-based v_available view); "
        "replaced by ChannelInventoryService + Soft Reserve tests "
        "in test_channel_inventory_available.py and test_order_reserve_anti_oversell.py"
    )
)
