# app/services/fsku_service_utils.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


FskuShape = Literal["single", "bundle"]


def normalize_shape(v: str | None) -> FskuShape:
    if v is None:
        return "bundle"
    s = v.strip()
    if not s:
        return "bundle"
    if s not in ("single", "bundle"):
        raise ValueError("shape must be 'single' or 'bundle'")
    return s  # type: ignore[return-value]


def normalize_code(v: str | None) -> str | None:
    if v is None:
        return None
    s = v.strip()
    return s or None
