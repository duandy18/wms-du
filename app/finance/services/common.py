from __future__ import annotations

from datetime import date
from decimal import Decimal
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


async def ensure_default_range(
    session: AsyncSession,
    *,
    from_dt: Optional[date],
    to_dt: Optional[date],
) -> tuple[date, date]:
    """
    财务分析默认窗口：最近 30 天，含 today。
    调用方明确传 from_date/to_date 时，以调用方为准。
    """
    if from_dt is not None and to_dt is not None:
        return from_dt, to_dt

    row = (await session.execute(text("SELECT current_date AS today"))).mappings().first()
    today: date = row["today"]  # type: ignore[assignment]
    return date.fromordinal(today.toordinal() - 29), today


def clean_platform(value: Optional[str]) -> str:
    return (value or "").strip().upper()


def clean_shop_id(value: Optional[str]) -> str:
    return (value or "").strip()


def to_decimal(value: object, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def ratio(numerator: Decimal, denominator: Decimal, *, scale: str = "0.0001") -> Decimal | None:
    if denominator <= 0:
        return None
    return (numerator / denominator).quantize(Decimal(scale))
