# app/adapters/registry.py
from __future__ import annotations
from typing import Dict

from app.adapters.base import ChannelAdapter
from app.adapters.pdd import PddAdapter


# 简单注册表：按 platform 选择适配器
_ADAPTERS: Dict[str, ChannelAdapter] = {
    "pdd": PddAdapter(),
    # 预留： "tb": TbAdapter(), "jd": JdAdapter(), ...
}


def get_adapter(platform: str) -> ChannelAdapter:
    key = (platform or "pdd").lower()
    if key not in _ADAPTERS:
        # 默认回落到 pdd（或抛错也可）
        return _ADAPTERS["pdd"]
    return _ADAPTERS[key]
