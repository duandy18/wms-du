# app/api/routers/finance_overview_helpers.py
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def parse_date_param(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    return date.fromisoformat(v)


async def ensure_default_7d_range(
    session: AsyncSession,
    *,
    from_dt: Optional[date],
    to_dt: Optional[date],
) -> tuple[date, date]:
    """
    行为保持与原实现一致：
    - 若 from_dt 或 to_dt 任一为空，则以 DB 的 current_date 为 today
    - 默认范围：最近 7 天（含 today）：[today-6, today]
    """
    if from_dt is not None and to_dt is not None:
        return from_dt, to_dt

    sql_default = text("SELECT current_date AS today")
    today_row = (await session.execute(sql_default)).mappings().first()
    today: date = today_row["today"]  # type: ignore[assignment]
    to_dt2 = today
    from_dt2 = date.fromordinal(today.toordinal() - 6)
    return from_dt2, to_dt2


def clean_platform(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def clean_shop_id(value: Optional[str]) -> str:
    return (value or "").strip()
