"""
Legacy: StockService 出库幂等边界测试（基于 location_id）。

场景：
  - InboundService.receive + StockService.adjust(location_id, ...);
  - 通过 ref/ref_line 组合模拟出库幂等。

当前：
  - 幂等出库行为由 v2 OutboundService/StockService + 对应 v2 测试覆盖；
  - 旧 location_id 口径不再适用。

本文件标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy stock idempotency edge tests on (item_id, location_id); "
        "superseded by v2 OutboundService/StockService tests using warehouse/batch."
    )
)
