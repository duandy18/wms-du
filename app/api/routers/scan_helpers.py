# app/api/routers/scan_helpers.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def to_date_str(v: Any) -> Optional[str]:
    """
    将 date / datetime / str 统一转为 'YYYY-MM-DD' 字符串，其他类型兜底为 str(v)。
    用于 ScanResponse 的 production_date / expiry_date，避免 Pydantic 类型错误。
    """
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s or None
    if isinstance(v, datetime):
        return v.date().isoformat()
    try:
        iso = getattr(v, "isoformat", None)
        if callable(iso):
            return iso()
    except Exception:
        pass
    return str(v)
