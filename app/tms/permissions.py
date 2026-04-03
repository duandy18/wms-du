# app/tms/permissions.py
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.user.services.user_service import AuthorizationError, UserService


def check_config_perm(db: Session, current_user, required: list[str]) -> None:
    svc = UserService(db)
    try:
        svc.check_permission(current_user, required)
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized.")
