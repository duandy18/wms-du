# app/services/stock_adjust/meta.py
from __future__ import annotations

from typing import Any, Dict, Optional


def meta_bool(meta: Optional[Dict[str, Any]], key: str) -> bool:
    if not meta:
        return False
    return meta.get(key) is True


def meta_str(meta: Optional[Dict[str, Any]], key: str) -> Optional[str]:
    if not meta:
        return None
    v = meta.get(key)
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError(f"meta.{key} 必须为字符串")
    s = v.strip()
    return s or None
