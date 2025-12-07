"""
Legacy: putaway handler（两腿移库）的单元/合同测试。

原目标：
  - handle_putaway 写两腿库存（from_loc -qty / to_loc +qty）；
  - 为每条 leg 写入正确的 ref/ref_line/batch_code/日期；
  - 作为扫描 PUTAWAY 的主要实现。

当前实现中：
  - app.services.scan_handlers.putaway_handler.handle_putaway 直接抛出
    FeatureDisabled('FEATURE_DISABLED: putaway')，表示该功能在现阶段关闭。

因此，本文件标记为 legacy，不再参与当前测试基线。
"""

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "legacy putaway handler tests: putaway is explicitly disabled "
        "(FeatureDisabled: putaway); will be redesigned if re-enabled "
        "on top of the v2 stock model."
    )
)
