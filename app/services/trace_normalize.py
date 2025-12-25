# app/services/trace_normalize.py
from __future__ import annotations

from datetime import datetime, timezone


def normalize_ts(ts: datetime | None) -> datetime | None:
    """
    统一时间为 tz-aware UTC，避免 naive / aware 混用导致排序报错。
    """
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)
