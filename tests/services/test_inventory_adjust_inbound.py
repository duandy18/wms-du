"""
Legacy: 入库场景测试（InventoryAdjust + InboundService v1）。

当前（Phase 4E）：
  - 入库已统一走 lot-world 模型；
  - 旧签名不再适用。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy inventory inbound tests using InboundService.receive(location_id); "
        "Phase 4E inbound uses warehouse+lot."
    )
)
