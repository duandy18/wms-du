"""
Legacy: 入库场景测试（InventoryAdjust + InboundService v1）。

依赖：
  - InboundService.receive(session, item_id, location_id, qty, ref, ...);
  - 基于 location_id 的库存槽位。

当前：
  - 入库已统一走 v2 批次/仓库模型；
  - InboundService.receive 签名已变化，不再接受 location_id 参数。

本文件标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy inventory inbound tests using InboundService.receive(location_id); "
        "inbound flow has been refactored to v2 warehouse/batch model."
    )
)
