"""
Legacy: StockService + InboundService v1 合同测试（基于 location_id）。

原合同依赖：
  - InboundService.receive(session, item_id, location_id, qty, ref, ...);
  - StockService.adjust(session, item_id, location_id, delta, ...);
  - legacy stocks_legacy 表存在 location_id/batch_id 等列。

当前实现（Phase 4E）：
  - 余额事实源：stocks_lot
  - 批次主档：lots
  - 台账事实：stock_ledger
  - 旧 location_id 口径不再适用

v2 行为由 test_stock_service_v2.py、quick inbound 测试 等覆盖。
本文件标记为 legacy，不参与当前基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy stock/inbound contract tests based on location_id; "
        "Phase 4E uses (warehouse_id, item_id, lot_code) on top of lots+stocks_lot."
    )
)
