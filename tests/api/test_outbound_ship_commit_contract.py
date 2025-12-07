"""
Legacy: 出库链路 + 审计顺序（ORDER_CREATED -> SHIP_COMMIT）的 v1 合同测试。

原设计：
  - 使用 OutboundService.commit(session, platform, shop_id, ref,
        lines=[OutboundLine(item_id, location_id, qty)], mode='FEFO', ...) 构造出库；
  - 然后手工插入 ORDER_CREATED / SHIP_COMMIT 审计，检查：
      1) ledger.reason 仅为原子动作（PICK/PUTAWAY/INBOUND/COUNT/ADJUST），不含 OUTBOUND/SHIPMENT；
      2) audit_events 中 flow='OUTBOUND' 存在；
      3) ORDER_CREATED 在 SHIP_COMMIT 之前。

当前：
  - v2 出库链路通过 OutboundService.commit(order_id, lines=[{warehouse_id,item_id,batch_code,qty}], ...)
    和 ShipService.commit(/outbound/ship/commit) 实现；
  - 对 ORDER_CREATED / SHIP_COMMIT 审计链的验证由 v2 测试组合覆盖：
      * tests/services/test_order_outbound_flow_v3.py
      * tests/api/test_outbound_ship_commit_http.py 等。

因此，本文件作为旧世界合同文档，现标记为 legacy，不再执行。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy outbound ship chain contract using OutboundService v1 FEFO API; "
        "replaced by v2 order+ship+audit tests (see test_order_outbound_flow_v3 "
        "and test_outbound_ship_commit_http)."
    )
)
