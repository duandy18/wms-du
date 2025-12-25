# app/gateway/scan_orchestrator_dates.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def coerce_date(v: Any) -> Optional[date]:
    """
    将各种输入类型统一转换为 date 对象。非法则返回 None，由下游校验。
    支持：date/datetime、'YYYY-MM-DD'、'YYYYMMDD'、数值 20260101。
    """
    if v is None:
        return None

    if isinstance(v, (int, float)):
        v = str(int(v))

    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except Exception:
            pass
        if len(s) == 8 and s.isdigit():
            try:
                return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
            except Exception:
                return None
    return None


def date_to_json(v: Any) -> Optional[str]:
    """用于审计：把 date 转成 ISO 字符串，其他类型一律返回 None。"""
    if isinstance(v, date):
        return v.isoformat()
    return None
