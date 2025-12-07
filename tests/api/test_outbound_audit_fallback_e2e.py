"""
Legacy: 出库审计 Fallback E2E（基于 OutboundService v1 FEFO 接口）的 HTTP 合同测试。

原合同依赖：
  - from app.services.outbound_service import OutboundLine, OutboundService
  - OutboundService.commit(session, platform, shop_id, ref,
        lines=[OutboundLine(item_id, location_id, qty)], mode='FEFO', ...)

当前实现：
  - OutboundService v2 使用 (order_id, warehouse_id, item_id, batch_code, qty) 粒度；
  - FEFO 自动分配改由 v2 FefoAllocator/StockFallbacks 建议，不再隐藏在 OutboundService.commit 内；
  - 出库审计链路由 test_outbound_service_adjust_path.py、
    test_order_outbound_flow_v3.py 等 v2 tests 覆盖。

本文件保留为旧合同文档，不再参与当前测试基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy outbound audit fallback E2E test based on OutboundService v1 "
        "FEFO API (platform/shop_id/location_id/mode); "
        "v2 outbound/audit behavior is covered by v2 tests."
    )
)
