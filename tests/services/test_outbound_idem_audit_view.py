"""
Legacy: outbound 幂等 +审计视图（v1 FEFO + platform/mode 接口）测试。

原合同依赖：
  - OutboundService.commit(session, platform, shop_id, ref, lines=[OutboundLine(item_id, location_id, qty)], mode='FEFO', ...);
  - 通过旧视图/表结构检查审计与幂等。

当前实现：
  - OutboundService v2 以 (order_id, warehouse_id, item_id, batch_code) 粒度工作【commit(order_id, lines=..., occurred_at)】；
  - 旧的 platform/mode/location_id 入口已退役；
  - v2 行为由 test_outbound_service_adjust_path.py 等测试覆盖。

本文件保留为历史合同文档，现标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy outbound idempotency/audit tests based on OutboundService.commit("
        "platform, shop_id, location_id, mode='FEFO'); "
        "superseded by v2 outbound_service tests using (order_id, warehouse, batch_code)."
    )
)
