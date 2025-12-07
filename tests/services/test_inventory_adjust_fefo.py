"""
Legacy: FEFO 出库 + allow_expired 组合测试（基于 OutboundService v1）。

依赖：
  - OutboundService.commit(session, platform, shop_id, ref,
      lines=[OutboundLine(item_id, location_id, qty)], mode='FEFO', ...)

当前：
  - OutboundService 已改为显式 ShipLine(warehouse_id, item_id, batch_code, qty) 风格，
    不再接受 platform/shop_id/mode 等旧参数；
  - FEFO 出库路径由 v2 OutboundService + FefoAllocator/StockFallbacks 组合实现。

本文件标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy FEFO outbound tests using OutboundService.commit(platform, shop_id, location_id,...); "
        "OutboundService v2 no longer supports this signature."
    )
)
