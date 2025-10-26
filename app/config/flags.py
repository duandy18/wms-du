"""
WMS-DU Feature Flags
--------------------
所有跨边界功能（渠道推送、多平台、多仓）统一在这里开关。
默认全关，可通过环境变量启用：
  export ENABLE_PDD_PUSH=true
  export ENABLE_TB=true
"""

from __future__ import annotations
import os


def _bool(name: str, default: bool = False) -> bool:
    """读取布尔环境变量。"""
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


# === Phase 0：PDD 渠道能力 ===
ENABLE_PDD_PULL = _bool("ENABLE_PDD_PULL", False)
ENABLE_PDD_PUSH = _bool("ENABLE_PDD_PUSH", False)

# === Phase 3：多平台预留 ===
ENABLE_TB = _bool("ENABLE_TB", False)
ENABLE_JD = _bool("ENABLE_JD", False)
ENABLE_DY = _bool("ENABLE_DY", False)

# === Phase 4：多仓预留 ===
ENABLE_MULTI_WAREHOUSE = _bool("ENABLE_MULTI_WAREHOUSE", False)

# === Phase X：调试/实验开关（可自定义） ===
ENABLE_DEV_METRICS = _bool("ENABLE_DEV_METRICS", False)
