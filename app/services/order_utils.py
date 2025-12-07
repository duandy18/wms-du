# app/services/order_utils.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

UTC = timezone.utc


def to_dec_str(x: Decimal | int | float | str | None, default: str = "0") -> str:
    """
    统一把各种金额类型转成字符串形式的 Decimal，避免浮点精度问题。
    """
    if x is None:
        return default
    try:
        return str(Decimal(str(x)))
    except (InvalidOperation, ValueError):
        return default


def to_int_pos(x: Any, default: int = 0) -> int:
    """
    转成正整数，不合法或 <=0 时返回默认值。
    """
    try:
        v = int(x)
        return v if v > 0 else default
    except Exception:
        return default


def parse_dt(x: Any) -> datetime:
    """
    把平台传来的时间字段统一转成 tz-aware datetime（UTC）。
    """
    if isinstance(x, datetime):
        return x if x.tzinfo is not None else x.replace(tzinfo=UTC)
    return datetime.now(UTC)


def to_float(x: Any, default: float = 0.0) -> float:
    """
    宽松地把任意输入转成 float，用于金额/数量临时计算（最终金额仍应走 Decimal）。
    """
    try:
        return float(x)
    except Exception:
        return default
