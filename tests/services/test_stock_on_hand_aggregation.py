"""
Legacy: StockService.get_on_hand(location_id, batch_code) 聚合测试。

依赖：
  - StockService.get_on_hand(session, item_id, location_id, batch_code)
  - 旧的 stocks(item_id, location_id, batch_id, qty) 模式。

当前：
  - StockService 不再暴露 get_on_hand(location_id) 接口；
  - 在库聚合通过 v2 模型/视图 & 快照测试覆盖。

本文件作为旧 API 文档，现标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy get_on_hand aggregation tests based on location_id; "
        "StockService v2 no longer exposes get_on_hand(location_id)."
    )
)
