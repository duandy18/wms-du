"""
Legacy: StockService 出库幂等边界测试（基于 location_id）。

当前（Phase 4E）：
  - 幂等出库行为由 v2 OutboundService/StockService + 对应 v2 测试覆盖；
  - 旧 location_id 口径不再适用。

本文件标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy stock idempotency edge tests on (item_id, location_id); "
        "superseded by Phase 4E OutboundService/StockService tests using warehouse/lot."
    )
)
