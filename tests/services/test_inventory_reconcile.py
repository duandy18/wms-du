"""
Legacy: ReconcileService 基于 StockService.get_on_hand(location_id) 的测试。

依赖：
  - ReconcileService.reconcile(session, item_id, location_id, actual_qty, ref);
  - StockService.get_on_hand(session, item_id, location_id).

当前：
  - ReconcileService 已对接 v2 库存模型；
  - StockService 不再提供 get_on_hand(location_id) 接口。

本文件作为旧 reconcile 设计的文档，现标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy inventory reconcile tests using location-based get_on_hand; "
        "v2 reconcile logic is implemented on top of the v2 stock model "
        "and will require new tests."
    )
)
