"""
Legacy: scan PUTAWAY 模式（两腿移库）的合同测试。

原合同要求：
  - mode='putaway' 的 probe 请求写入 event_log.source='scan_putaway_probe'；
  - commit 请求实际移动库存，两腿各一条 COUNT/ADJUST 账；
  - /scan 网关对 putaway 模式视为一等路径。

当前实现中：
  - app.services.scan_handlers.putaway_handler.handle_putaway 明确抛出 FeatureDisabled，
    表示 Putaway 功能在现版本中被关闭/占位；
  - scan_orchestrator 对未识别/禁用的 mode 统一记录为 'scan_other_mode'。

Putaway 已不再作为 Phase 3.x 主体能力，后续若重启该功能，将以新的批次/仓库模型
重新设计 Handler 与测试。

故本文件标记为 legacy，不参与当前测试基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy scan/putaway tests: putaway handler is currently disabled "
        "(FeatureDisabled: putaway); will be refit if/when putaway is reintroduced "
        "on top of the v2 (warehouse,item,batch) model."
    )
)
