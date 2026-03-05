# app/services/platform_order_resolve_utils.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List


def norm_platform(v: str) -> str:
    return (v or "").strip().upper()


def norm_shop_id(v: str) -> str:
    return str(v or "").strip()


def to_int_pos(v: Any, *, default: int = 1) -> int:
    try:
        n = int(v)
        return n if n > 0 else default
    except Exception:
        return default


def to_dec(v: Any) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def dec_to_int_qty(q: Decimal) -> int:
    if q <= 0:
        return 0
    if q == q.to_integral_value():
        return int(q)
    raise ValueError(f"component qty must be integer-like, got={str(q)}")


# ---------------- Risk helpers ----------------
def _risk(level: str, flags: List[str], reason: str) -> Dict[str, Any]:
    return {
        "risk_flags": list(flags),
        "risk_level": str(level),
        "risk_reason": str(reason),
    }


def risk_high(flag: str, reason: str) -> Dict[str, Any]:
    return _risk("HIGH", [flag], reason)


def risk_medium(flag: str, reason: str) -> Dict[str, Any]:
    return _risk("MEDIUM", [flag], reason)


@dataclass
class ResolvedLine:
    filled_code: str
    qty: int
    fsku_id: int
    expanded_items: List[Dict[str, Any]]
