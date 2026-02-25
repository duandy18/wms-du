"""
Legacy: StockService.get_on_hand(location_id, batch_code) 聚合测试。

当前（Phase 4E）：
  - 在库聚合通过 lot-world（stocks_lot）与快照/三账测试覆盖。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy get_on_hand aggregation tests based on location_id; "
        "Phase 4E uses stocks_lot for on_hand aggregation."
    )
)
