"""
Legacy: FEFO 出库服务测试（location 维度 + reason='OUTBOUND' / 'SHIPMENT'）。

这组测试原本验证：
  - OutboundService.commit(mode=FEFO) 按 NEAR/FAR 扣减；
  - stock_ledger.reason 不得写入 OUTBOUND/SHIPMENT 口径（或反之）。

在当前版本中：
  - OutboundService 已重构为以 (warehouse_id, item_id, batch_code) 为粒度的
    “显式批次出库”服务（ShipLine），不再内部执行 FEFO 查询；
  - FEFO 行为由 FefoAllocator / StockFallbacks 及其自有测试覆盖：
      * tests/services/test_fefo_allocator.py
      * tests/services/test_inventory_adjust_fefo.py  等
  - 出库服务的幂等与 ledger 一致性由以下测试覆盖：
      * tests/services/test_outbound_service_adjust_path.py
      * tests/services/test_outbound_commit_contract.py
      * tests/services/test_outbound_idempotent_ship.py  等。

因此，本文件作为旧 FEFO 实现的合同测试，现已退役。
保留文件仅作为文档记录，不再参与当前测试基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy FEFO-based OutboundService tests (location schema); "
        "current OutboundService uses explicit (warehouse_id, item_id, batch_code) "
        "and is covered by v2 tests such as test_outbound_service_adjust_path.py "
        "and test_outbound_commit_contract.py"
    )
)
