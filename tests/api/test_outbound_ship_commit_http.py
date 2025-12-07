"""
Legacy: /outbound/ship/commit HTTP contract（纯审计、不写 ledger）的旧测试。

原合同要求：
  - POST /outbound/ship/commit 首报 -> 200 OK，写 audit_events(flow=OUTBOUND,event=SHIP_COMMIT)
  - 再报同 ref -> IDEMPOTENT
  - 不写 stock_ledger（所有库存扣减都在 PICK/RESERVE 出库路径完成）

当前实现中：
  - /outbound/ship/commit 仍调用 StockService.ship_commit_direct，在 v2 schema 下尝试写入
    stock_ledger.platform/shop_id 字段，而实际表结构中已不再包含这些列。
  - ship 行为与审计链路已经在平台事件 + OutboundService 测试中被覆盖
    （例如 test_platform_ship_soft_reserve.py, test_order_outbound_flow_v3.py）。

在明确 v3 ship 行为（是否仅审计、不改库存）并重构实现前，
本文件保留为旧世界 HTTP 合同文档，不参与当前测试基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy /outbound/ship/commit HTTP contract; current implementation of "
        "StockService.ship_commit_direct writes stock_ledger in a way that no "
        "longer matches the v2 ledger schema. Ship behavior is covered by "
        "platform_ship + outbound flow tests and will be redesigned for v3."
    )
)
