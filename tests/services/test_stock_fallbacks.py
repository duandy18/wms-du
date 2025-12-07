"""
Legacy: 旧 StockFallbacks + StockService(location_id) 组合测试。

内容包括：
  - COUNT 并发下的单条 ledger 保障；
  - PUTAWAY 参考线连续性；
  - PICK vs COUNT / PICK vs PICK 并发场景。

这些测试依赖：
  - StockService.adjust(session, item_id, location_id, ...);
  - 底层 stocks.location_id 列。

当前：
  - FEFO/fallback 逻辑已重写为 v2 FefoAllocator/StockFallbacks，
    使用 (item_id, warehouse_id, batch_code) + stocks.qty；
  - 旧 location 口径的 fallback 测试不再适用。

本文件标记为 legacy，待未来按新 FefoAllocator + v2 库存模型重写测试集。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy StockFallbacks tests using StockService.adjust(location_id); "
        "fallback/FEFO behavior has been redesigned on top of v2 stocks "
        "and will need new tests."
    )
)
