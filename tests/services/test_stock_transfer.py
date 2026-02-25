"""
Legacy: test_stock_transfer_fefo 基于旧 FEFO + location_id 的测试。

依赖：
  - 直接访问 legacy stocks_legacy.location_id / batches_legacy.location_id 等列。

当前（Phase 4E）：
  - FEFO 分配器已重构为 lot-world（warehouse_id,item_id,lot_code）。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy stock transfer FEFO test depending on location_id; "
        "Phase 4E FEFO allocator uses warehouse+lot on lots+stocks_lot."
    )
)
