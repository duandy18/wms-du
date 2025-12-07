"""
Legacy: putaway handler 合同测试（批次透传 + 两腿 delta）。

与 test_putaway_handler.py 相同，本文件是一组针对旧 putaway 实现的合同约束：
  - 负腿/正腿各 1 次；
  - 批次 batch_code 两腿一致；
  - 可选断言 warehouse_id 透传等。

当前 putaway handler 已显式 FeatureDisabled，不再执行两腿移库逻辑。

因此，本文件标记为 legacy。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy putaway contract tests: current putaway handler is FeatureDisabled; "
        "putaway flow is not part of the Phase 3.6 baseline."
    )
)
