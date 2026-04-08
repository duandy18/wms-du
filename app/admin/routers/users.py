# app/admin/routers/users.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.admin.contracts.user_permission_matrix import (
    PermissionMatrixRowOut,
    UserPermissionMatrixOut,
)
from app.admin.contracts.user_permission_matrix_update import UserPermissionMatrixUpdateIn
from app.admin.services.user_permission_matrix_service import UserPermissionMatrixService
from app.admin.services.user_permission_matrix_write_service import (
    UserPermissionMatrixWriteService,
)
from app.db.session import get_db
from app.user.contracts.user import UserOut
from app.user.contracts.user_admin import (
    PasswordResetIn,
    UserCreateMulti,
    UserUpdateMulti,
)
from app.user.deps.auth import get_current_user
from app.user.services.user_service import DuplicateUserError, NotFoundError, UserService

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
    svc = UserService(db)
    svc.check_permission(current_user, ["page.admin.read"])

    matrix_service = UserPermissionMatrixService(db)
    return matrix_service.get_matrix()


@router.put("/{user_id}/permission-matrix", response_model=PermissionMatrixRowOut)
def update_user_permission_matrix(
    user_id: int,
    body: UserPermissionMatrixUpdateIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)
    svc.check_permission(current_user, ["page.admin.write"])

    matrix_write_service = UserPermissionMatrixWriteService(db)
    try:
        return matrix_write_service.update_matrix_for_user(
            user_id=user_id,
            actor_user_id=int(getattr(current_user, "id")),
            body=body,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreateMulti,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)
    svc.check_permission(current_user, ["page.admin.write"])

    try:
        user = svc.create_user(
            username=body.username,
            password=body.password,
            permission_ids=body.permission_ids,
            full_name=body.full_name,
            phone=body.phone,
            email=body.email,
        )
        return _to_user_out(svc, user)
    except (DuplicateUserError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)
    svc.check_permission(current_user, ["page.admin.read"])

    users = svc.list_users()
    return [_to_user_out(svc, u) for u in users]


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdateMulti,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)
    svc.check_permission(current_user, ["page.admin.write"])

    try:
        user = svc.update_user(
            user_id=user_id,
            actor_user_id=int(getattr(current_user, "id")),
            full_name=body.full_name,
            phone=body.phone,
            email=body.email,
            is_active=body.is_active,
        )
        return _to_user_out(svc, user)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_id}/delete")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)
    svc.check_permission(current_user, ["page.admin.write"])

    if int(getattr(current_user, "id")) == int(user_id):
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")

    try:
        svc.delete_user(
            user_id=user_id,
            actor_user_id=int(getattr(current_user, "id")),
        )
        return {"ok": True, "message": "用户已删除"}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    _: PasswordResetIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)
    svc.check_permission(current_user, ["page.admin.write"])

    try:
        svc.reset_user_password(
            user_id,
            new_password="000000",
            actor_user_id=int(getattr(current_user, "id")),
        )
        return {"ok": True, "message": "密码重置为 000000"}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"重置密码失败: {e}")


__all__ = ["router"]
