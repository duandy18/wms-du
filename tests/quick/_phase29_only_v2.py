import os
import pathlib
import re

import pytest

# Phase 2.9：默认只跑 v2 核心用例（PHASE29_ONLY_V2="1"）
# Phase 3.x：我们改为默认关闭这个闸门，让所有 quick 按各自文件逻辑运行。
# 如需恢复 Phase 2.9 行为，可在环境中显式设置：
#   export PHASE29_ONLY_V2=1
ONLY_V2 = os.getenv("PHASE29_ONLY_V2", "0")

# 允许直接运行的文件名模式（_v2 结尾或特定核心用例）
ALLOW = re.compile(r"(?:_v2\.py$|test_outbound_core_v2\.py$)")


def _is_only_v2_enabled() -> bool:
    v = str(ONLY_V2)
    return v in ("1", "true", "True", "yes", "on")


def pytest_collection_modifyitems(config, items):
    """
    当 PHASE29_ONLY_V2 显式开启时，只保留 v2 核心 quick 用例，
    其余一律标记为 skip（用于旧基线下快速跑核心用例）。

    Phase 3.x 默认关闭此行为，由各测试文件自身的 skip 决定是否跳过。
    """
    if not _is_only_v2_enabled():
        return

    skipped = pytest.mark.skip(
        reason="Phase 2.9 仅验证 (warehouse,item,batch)+qty 的 v2 核心；非 v2 用例已暂挂，Phase 3 回收"
    )
    for it in items:
        p = pathlib.Path(str(it.fspath))
        if not ALLOW.search(p.name):
            it.add_marker(skipped)
