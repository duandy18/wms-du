# app/utils/time.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))  # Asia/Shanghai (+08:00)


def to_cst(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        # 假定传入是 UTC naive
        return dt.replace(tzinfo=timezone.utc).astimezone(CST)
    return dt.astimezone(CST)
