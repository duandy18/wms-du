# app/services/platform_events_adapters.py
from __future__ import annotations

from typing import Dict

from app.services.platform_adapter import (
    DouyinAdapter,
    JDAdapter,
    PDDAdapter,
    PlatformAdapter,
    TaobaoAdapter,
    TmallAdapter,
    XHSAdapter,
)

_ADAPTERS: Dict[str, PlatformAdapter] = {
    "pdd": PDDAdapter(),
    "taobao": TaobaoAdapter(),
    "tmall": TmallAdapter(),
    "jd": JDAdapter(),
    "douyin": DouyinAdapter(),
    "xhs": XHSAdapter(),
}


def get_adapter(platform: str) -> PlatformAdapter:
    ad = _ADAPTERS.get((platform or "").lower())
    if not ad:
        raise ValueError(f"Unsupported platform: {platform}")
    return ad
