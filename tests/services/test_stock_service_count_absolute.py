"""
Legacy: 绝对盘点（COUNT absolute）基于旧 StockService 接口的测试。

依赖：
  - InboundService.receive(..., location_id=...);
  - StockService.adjust(..., location_id=...).

当前版本：
  - 盘点 & 入库逻辑已迁移到 v2 库存模型；
  - 旧合同由新的 count/reconcile 测试取代。

本文件作为历史行为记录，暂时跳过。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy COUNT-absolute tests using StockService.adjust(location_id) "
        "and InboundService.receive(location_id); superseded by v2 stock/reconcile tests."
    )
)
