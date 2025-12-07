"""
Legacy: StockService + InboundService v1 合同测试（基于 location_id）。

原合同依赖：
  - InboundService.receive(session, item_id, location_id, qty, ref, ...);
  - StockService.adjust(session, item_id, location_id, delta, ...);
  - stocks 表存在 location_id/batch_id 等列。

当前实现：
  - StockService 已升级为 (item_id, warehouse_id, batch_code) 粒度；
  - InboundService.receive 使用 v2 批次/仓库模型；
  - stocks 不再有 location_id/batch_id 列。

v2 行为由 test_stock_service_v2.py、quick inbound 测试 等覆盖。
本文件标记为 legacy，不参与当前基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy stock/inbound contract tests based on location_id; "
        "StockService & InboundService now use (warehouse_id, item_id, batch_code) "
        "and are covered by v2/unit & quick tests."
    )
)
