# app/pms/projections/routers/deps.py
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.pms.projections.services.pms_projection_service import PmsProjectionService
from app.user.deps.auth import get_current_user
from app.user.services.user_service import UserService


def get_pms_projection_service(db: Session = Depends(get_db)) -> PmsProjectionService:
    return PmsProjectionService(db)


def require_pms_projection_read(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)
    svc.check_permission(current_user, ["page.pms.read"])
    return current_user


def require_pms_projection_write(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)
    svc.check_permission(current_user, ["page.pms.write"])
    return current_user


PmsProjectionServiceDep = Annotated[
    PmsProjectionService,
    Depends(get_pms_projection_service),
]
PmsProjectionReadUserDep = Annotated[
    object,
    Depends(require_pms_projection_read),
]
PmsProjectionWriteUserDep = Annotated[
    object,
    Depends(require_pms_projection_write),
]

__all__ = [
    "PmsProjectionReadUserDep",
    "PmsProjectionServiceDep",
    "PmsProjectionWriteUserDep",
]
