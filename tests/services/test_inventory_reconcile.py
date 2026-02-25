"""
Legacy: ReconcileService 基于 StockService.get_on_hand(location_id) 的测试。

当前（Phase 4E）：
  - reconcile 逻辑已对接 lot-world（stocks_lot）。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy inventory reconcile tests using location-based get_on_hand; "
        "Phase 4E reconcile uses stocks_lot + ledger."
    )
)
