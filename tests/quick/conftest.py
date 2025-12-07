# tests/quick/conftest.py
import os
import pathlib
import re

import pytest

# 默认：不开启 v2-only 过滤
# 只有当 PHASE29_ONLY_V2 显式设置为 "1"/"true"/"True" 时，才启用筛选。
ONLY_V2 = os.getenv("PHASE29_ONLY_V2", "0")

# 当 v2-only 模式开启时，允许的 quick 测试：
# - *_v2.py                     （所有 v2 文件）
# - test_outbound_core_v2.py    （核心 V2 出库测试）
# - test_inbound_smoke_pg.py    （v2 入库烟雾测试）
ALLOW = re.compile(r"(?:_v2\.py$|test_outbound_core_v2\.py$|test_inbound_smoke_pg\.py$)")


def pytest_collection_modifyitems(config, items):
    """
    Quick 测试筛选策略：

    - 默认（PHASE29_ONLY_V2 未设置或为 0）：
        不做任何过滤，所有 tests/quick 下的用例正常收集、运行。

    - 若显式设置 PHASE29_ONLY_V2=1：
        仅运行文件名匹配 ALLOW 的 quick 测试；
        其余 quick 测试统一 skip，用于只跑“v2 核心集”的场景。
    """
    if ONLY_V2 not in ("1", "true", "True"):
        return

    skipped = pytest.mark.skip(
        reason=(
            "Phase 2.9 仅验证 (warehouse,item,batch)+qty 的 v2 核心；"
            "非 v2 用例暂挂，手动设置 PHASE29_ONLY_V2=0 时恢复"
        )
    )

    for it in items:
        name = pathlib.Path(str(it.fspath)).name
        if not ALLOW.search(name):
            it.add_marker(skipped)
