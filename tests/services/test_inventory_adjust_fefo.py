"""
Legacy: FEFO 出库 + allow_expired 组合测试（基于 OutboundService v1）。

当前（Phase 4E）：
  - OutboundService 已统一为 lot-world；
  - 旧签名不再适用。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy FEFO outbound tests using OutboundService.commit(..., location_id,...); "
        "Phase 4E OutboundService uses warehouse+lot."
    )
)
