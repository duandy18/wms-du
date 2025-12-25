# app/api/routers/shipping_quote_helpers.py
from __future__ import annotations

from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.user_service import AuthorizationError, UserService


def check_perm(db: Session, user, perm: str) -> None:
    svc = UserService(db)
    try:
        svc.check_permission(user, [perm])
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized")


def dims_from_payload(
    length_cm: Optional[float], width_cm: Optional[float], height_cm: Optional[float]
) -> Optional[Tuple[float, float, float]]:
    if length_cm is None or width_cm is None or height_cm is None:
        return None
    return (float(length_cm), float(width_cm), float(height_cm))
