"""
Legacy: test_stock_transfer_fefo 基于旧 FEFO + location_id 的测试。

依赖：
  - FefoAllocator.plan(session, item_id, location_id, ...);
  - 直接访问 stocks.location_id / batches.location_id 等列。

当前：
  - FEFO 分配器已重构为 v2 FefoAllocator(warehouse_id,item_id,batch_code)；
  - stocks 表不再有 location_id。

本文件作为旧 FEFO 设计的文档，现标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy stock transfer FEFO test depending on stocks.location_id; "
        "v2 FefoAllocator uses (warehouse_id, item_id, batch_code) and "
        "is covered by dedicated v2 tests."
    )
)
