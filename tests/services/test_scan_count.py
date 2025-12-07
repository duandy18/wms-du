"""
Legacy: scan COUNT 模式的 E2E 合同测试。

原合同：
  - /scan mode='count' 根据 on_hand/actual 差异写 COUNT 账；
  - resp['committed'] 必须为 True；
  - event_log.source 采用 scan_count_* 命名。

当前实现：
  - Count Handler 与 Scan Orchestrator 已按 v2 模型重构；
  - 旧合同中关于 resp['committed'] 与具体审计 source 的约定已不再适用。

Scan COUNT 将在单独的 Phase 中按新设计补齐合同测试。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy scan/count tests: COUNT flow and handlers refactored; "
        "old contracts on resp['committed'] and event_log source are no longer valid."
    )
)
