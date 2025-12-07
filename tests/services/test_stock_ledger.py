"""
Legacy: 基于 InboundService.receive(location_id, ...) 的账页写入测试。

原合同：
  - InboundService.receive(session, item_id, location_id, qty, ref, ...)；
  - 然后验证 stock_ledger 中是否有对应 ref / reason 记录。

当前：
  - InboundService 已升级为 v2 仓+批次模型（warehouse_id, batch_code）；
  - 账页写入由 ledger_writer / StockService.adjust + v2 测试覆盖。

本文件保留为旧账页口径文档，标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy stock ledger tests relying on InboundService.receive(location_id); "
        "ledger behavior is now driven by v2 stock_service/ledger_writer tests."
    )
)
