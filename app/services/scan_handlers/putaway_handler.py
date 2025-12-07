# app/services/scan_handlers/putaway_handler.py
from __future__ import annotations

from typing import Any, Dict


# v2 蓝图：putaway 已禁用；保留同名入口以保证旧引用不炸，但统一返回错误。
class FeatureDisabled(Exception):
    pass


async def handle_putaway(*args, **kwargs) -> Dict[str, Any]:
    raise FeatureDisabled("FEATURE_DISABLED: putaway")
