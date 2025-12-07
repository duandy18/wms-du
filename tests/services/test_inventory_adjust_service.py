"""
Legacy: InventoryAdjustService 基于 StockService.adjust(location_id) 的测试。

场景：
  - 先 +5 再 -3 的调整逻辑；
  - 负数防守等。

当前：
  - StockService.adjust 已统一为 (item_id, warehouse_id, batch_code)；
  - 绝大多数调整 / reconcile 流程由 v2 服务与测试覆盖。

本文件作为旧接口行为记录，现标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy inventory adjust tests: rely on StockService.adjust(location_id); "
        "adjustment logic is now covered by v2 stock/reconcile pipeline."
    )
)
