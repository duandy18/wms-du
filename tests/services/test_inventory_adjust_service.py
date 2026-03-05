"""
Legacy: InventoryAdjustService 基于 StockService.adjust(location_id) 的测试。

当前（Phase 4E）：
  - 调整/reconcile 流程由 lot-world 覆盖。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy inventory adjust tests rely on location_id; "
        "Phase 4E adjustment is covered by lot-world stock/reconcile tests."
    )
)
