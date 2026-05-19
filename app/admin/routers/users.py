# app/admin/routers/users.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.admin.contracts.user_permission_matrix import UserPermissionMatrixOut
from app.admin.services.user_permission_matrix_service import UserPermissionMatrixService
from app.db.session import get_db
from app.user.contracts.user import UserOut
from app.user.deps.auth import get_current_user
from app.user.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["admin-users"])


def _to_user_out(svc: UserService, user) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        full_name=user.full_name,
        phone=user.phone,
        email=user.email,
        permissions=svc.get_user_permissions(user),
    )


@router.get("/permission-matrix", response_model=UserPermissionMatrixOut)
def get_user_permission_matrix(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Read-only WMS local IAM runtime projection.

    ERP is the IAM owner. WMS keeps local users / user_permissions only for
    runtime permission execution and diagnostic visibility.
    """

    svc = UserService(db)
    svc.check_permission(current_user, ["page.admin.read"])

    matrix_service = UserPermissionMatrixService(db)
    return matrix_service.get_matrix()


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Read-only WMS local users runtime projection.

    User creation, status changes, password reset, deletion, and permission
    assignment are managed by ERP and applied through /system/write/v1/iam.
    """

    svc = UserService(db)
    svc.check_permission(current_user, ["page.admin.read"])

    users = svc.list_users()
    return [_to_user_out(svc, u) for u in users]


__all__ = ["router"]
