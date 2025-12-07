"""
Legacy: 基于 InboundService.receive(location_id) 的账页路由测试。

原测试：
  - 调用 InboundService.receive(session, item_id, location_id, ...) 生成账页；
  - 通过 API/路由层导出账页记录。

当前：
  - InboundService 已采用 v2 仓/批次接口；
  - stock_ledger 的结构与路由行为由新的 v2 测试覆盖（含导出接口）。

本文件作为旧路由合同文档，标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy stock ledger route tests using InboundService.receive(location_id); "
        "stock ledger routes will be validated by v2-specific tests."
    )
)
