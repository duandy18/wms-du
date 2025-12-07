"""
Legacy: outbound FEFO 幂等（v1）测试。

原场景：
  - OutboundService.commit(session, platform, shop_id, ref, lines=[OutboundLine(item_id, location_id, qty)], mode='FEFO', ...);
  - 验证同一 ref 下重放不重复扣减。

当前：
  - 出库幂等行为由 OutboundService v2 + stock_ledger 约束，并在
    test_outbound_service_adjust_path.py / test_order_outbound_flow_v3.py 等中覆盖；
  - 旧 platform/location/mode 接口不再存在。

本文件作为旧实现文档，标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy FEFO-based outbound idempotent ship tests using old OutboundService.commit "
        "signature; behavior is covered by v2 outbound tests."
    )
)
