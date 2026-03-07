# app/api/routers/shipping_provider_pricing_schemes_utils.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.user_service import AuthorizationError, UserService


# -----------------------
# Permission
# -----------------------
def check_perm(db: Session, user, perm: str) -> None:
    svc = UserService(db)
    try:
        svc.check_permission(user, [perm])
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized")


# -----------------------
# Validators / Normalizers
# -----------------------
_ALLOWED_MEMBER_LEVELS = {"province", "city", "district", "text"}


def norm_level(v: str) -> str:
    lvl = (v or "").strip().lower()
    if lvl not in _ALLOWED_MEMBER_LEVELS:
        raise HTTPException(status_code=422, detail="level must be one of: province/city/district/text")
    return lvl


def norm_nonempty(v: Optional[str], field: str) -> str:
    t = (v or "").strip()
    if not t:
        raise HTTPException(status_code=422, detail=f"{field} is required")
    return t


def validate_effective_window(effective_from: Optional[datetime], effective_to: Optional[datetime]) -> None:
    if effective_from is not None and effective_to is not None:
        if effective_to < effective_from:
            raise HTTPException(status_code=422, detail="effective_to must be >= effective_from")


def clean_list_str(values: Optional[List[str]]) -> List[str]:
    """
    - strip
    - drop empty
    - keep stable order + de-dup
    """
    out: List[str] = []
    seen = set()
    for x in values or []:
        t = (x or "").strip()
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out
