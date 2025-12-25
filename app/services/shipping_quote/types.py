# app/services/shipping_quote/types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Dest:
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _s(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    t = v.strip()
    return t if t else None
