"""
Legacy: 旧 StockFallbacks + StockService(location_id) 组合测试。

依赖：
  - StockService.adjust(session, item_id, location_id, ...);
  - 底层 legacy stocks_legacy.location_id 列。

当前（Phase 4E）：
  - FEFO/fallback 逻辑已重写为 lot-world 分配（stocks_lot + lots）。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy StockFallbacks tests using location_id; "
        "Phase 4E FEFO/fallback runs on lots+stocks_lot."
    )
)
