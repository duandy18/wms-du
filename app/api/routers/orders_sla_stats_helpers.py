# app/api/routers/orders_sla_stats_helpers.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def normalize_window(
    start: Optional[datetime],
    end: Optional[datetime],
) -> tuple[datetime, datetime]:
    """
    规范化时间窗口：
    - 默认：最近 7 天（基于 shipped_at）
    - 若只给一端，自动补另一端
    """
    now = datetime.now(timezone.utc)

    if end is None and start is None:
        end = now
        start = end - timedelta(days=7)
    elif end is None and start is not None:
        end = start + timedelta(days=7)
    elif end is not None and start is None:
        start = end - timedelta(days=7)

    assert start is not None and end is not None

    if end < start:
        start, end = end, start

    return start, end
