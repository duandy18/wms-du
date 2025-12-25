# app/api/routers/user_routes_admin.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserOut
from app.services.user_service import DuplicateUserError, NotFoundError, UserService

from app.api.routers.user_schemas import PasswordResetIn, UserCreateMulti, UserUpdateMulti


def register(router: APIRouter) -> None:
    @router.post("/register", response_model=UserOut, status_code=201)
    def register_user(
        body: UserCreateMulti,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        svc = UserService(db)
        svc.check_permission(current_user, ["system.user.manage"])

        try:
            user = svc.create_user(
                username=body.username,
                password=body.password,
                primary_role_id=body.primary_role_id,
                full_name=body.full_name,
                phone=body.phone,
                email=body.email,
                extra_role_ids=body.extra_role_ids,
            )

            return UserOut(
                id=user.id,
                username=user.username,
                role_id=user.primary_role_id,
                is_active=user.is_active,
                full_name=user.full_name,
                phone=user.phone,
                email=user.email,
            )

        except (DuplicateUserError, NotFoundError) as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/", response_model=list[UserOut])
    def list_users(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        svc = UserService(db)
        svc.check_permission(current_user, ["system.user.manage"])

        users = db.query(User).all()
        return [
            UserOut(
                id=u.id,
                username=u.username,
                role_id=u.primary_role_id,
                is_active=u.is_active,
                full_name=u.full_name,
                phone=u.phone,
                email=u.email,
            )
            for u in users
        ]

    @router.patch("/{user_id}", response_model=UserOut)
    def update_user(
        user_id: int,
        body: UserUpdateMulti,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        svc = UserService(db)
        svc.check_permission(current_user, ["system.user.manage"])

        try:
            user = svc.update_user(
                user_id=user_id,
                full_name=body.full_name,
                phone=body.phone,
                email=body.email,
                primary_role_id=body.primary_role_id,
                extra_role_ids=body.extra_role_ids,
                is_active=body.is_active,
            )

            return UserOut(
                id=user.id,
                username=user.username,
                role_id=user.primary_role_id,
                is_active=user.is_active,
                full_name=user.full_name,
                phone=user.phone,
                email=user.email,
            )
        except NotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/{user_id}/reset-password")
    def reset_password(
        user_id: int,
        _: PasswordResetIn,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        svc = UserService(db)
        svc.check_permission(current_user, ["system.user.manage"])

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(404, "用户不存在")

        from app.core.security import get_password_hash

        try:
            user.password_hash = get_password_hash("000000")
            db.commit()
            return {"ok": True, "message": "密码重置为 000000"}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"重置密码失败: {e}")
