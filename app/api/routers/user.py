# app/api/routers/user.py

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.role import Role
from app.schemas.token import Token
from app.schemas.user import UserLogin, UserOut
from app.services.user_service import (
    AuthorizationError,
    DuplicateUserError,
    NotFoundError,
    UserService,
)

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------
# 多角色版输入结构
# ---------------------------------------------------------

class UserCreateMulti(BaseModel):
    username: str
    password: str
    primary_role_id: int
    extra_role_ids: list[int] = []
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None


class UserUpdateMulti(BaseModel):
    primary_role_id: int | None = None
    extra_role_ids: list[int] | None = None
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool | None = None


class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str


class PasswordResetIn(BaseModel):
    pass


# ---------------------------------------------------------
# 登录（必须为 POST /users/login）
# ---------------------------------------------------------
@router.post("/login", response_model=Token, status_code=200)
def login(
    body: UserLogin,
    db: Session = Depends(get_db),
):
    svc = UserService(db)

    user = svc.authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = svc.create_token_for_user(user)
    return Token(access_token=token, token_type="bearer", expires_in=None)


# ---------------------------------------------------------
# 创建用户（多角色）
# ---------------------------------------------------------
@router.post("/register", response_model=UserOut, status_code=201)
def register_user(
    body: UserCreateMulti,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)

    # system.user.manage 权限
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


# ---------------------------------------------------------
# 用户列表
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# 更新用户（多角色 + 主角色 + 基本信息）
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# 当前用户信息 /users/me
# ---------------------------------------------------------
@router.get("/me")
def get_me(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = UserService(db)
    permissions = svc.get_user_permissions(current_user)

    # 查询所有关联角色
    rows = db.execute(
        text("""
            SELECT r.id, r.name
              FROM roles r
              JOIN user_roles ur ON ur.role_id = r.id
             WHERE ur.user_id = :uid
        """),
        {"uid": current_user.id},
    ).fetchall()

    roles = [{"id": rid, "name": name} for rid, name in rows]

    # 补上主角色（如不在 user_roles 中）
    if current_user.primary_role_id:
        primary = db.query(Role).filter(Role.id == current_user.primary_role_id).first()
        if primary:
            info = {"id": primary.id, "name": primary.name}
            if info not in roles:
                roles.insert(0, info)

    return {
        "id": current_user.id,
        "username": current_user.username,
        "roles": roles,
        "permissions": permissions,
    }


# ---------------------------------------------------------
# 修改密码（自助）
# ---------------------------------------------------------
@router.post("/change-password")
def change_password(
    body: PasswordChangeIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)
    try:
        svc.change_password(
            current_user.id,
            old_password=body.old_password,
            new_password=body.new_password,
        )
        return {"ok": True}
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="旧密码错误")
    except NotFoundError:
        raise HTTPException(status_code=404, detail="用户不存在")


# ---------------------------------------------------------
# 重置密码（管理员）
# ---------------------------------------------------------
@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    _: PasswordResetIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    svc = UserService(db)

    # 权限校验
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
