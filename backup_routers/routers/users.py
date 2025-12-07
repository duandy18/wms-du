# app/routers/users.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, constr
from sqlalchemy.orm import Session

from app.services.user_service import (
    UserService,
    AuthorizationError,
    DuplicateUserError,
    NotFoundError,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# -------------------------------------------------------------------
# 同步 Session 依赖（与其他路由的“三级兜底”一致，但针对 sync Session）
# -------------------------------------------------------------------
def _get_sync_session(request: Request) -> Session:
    """
    优先使用 app.deps.get_db_session / app.db.get_db_session；
    若都没有，则从 app.state.sync_sessionmaker 获取。
    """
    try:
        # 优先尝试统一依赖模块
        from app.deps import get_db_session as _dep_get_session  # type: ignore

        return _dep_get_session()
    except Exception:
        try:
            from app.db import get_db_session as _dep_get_session  # type: ignore

            return _dep_get_session()
        except Exception:
            maker = getattr(request.app.state, "sync_sessionmaker", None)
            if maker is None:
                raise RuntimeError(
                    "No sync sessionmaker available. "
                    "Provide app.deps.get_db_session / app.db.get_db_session "
                    "or set app.state.sync_sessionmaker in app.main."
                )
            return maker()  # type: ignore[call-arg]


# -------------------------------------------------------------------
# Pydantic 请求/响应模型
# -------------------------------------------------------------------
Username = constr(strip_whitespace=True, min_length=3, max_length=64)


class RegisterReq(BaseModel):
    username: Username
    password: constr(min_length=6, max_length=128)
    role_id: int = Field(..., ge=1)


class LoginReq(BaseModel):
    username: Username
    password: constr(min_length=1)


class ChangePasswordReq(BaseModel):
    old_password: constr(min_length=1)
    new_password: constr(min_length=6, max_length=128)


class AssignRoleReq(BaseModel):
    role_id: int = Field(..., ge=1)


class PermissionReq(BaseModel):
    permission: constr(strip_whitespace=True, min_length=1, max_length=128)


# -------------------------------------------------------------------
# 工具：从 Authorization 头取用户
# -------------------------------------------------------------------
def _bearer_token(authz: Optional[str]) -> Optional[str]:
    if not authz:
        return None
    parts = authz.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _current_user_or_none(db: Session, token: Optional[str]):
    if not token:
        return None
    svc = UserService(db)
    return svc.get_user_from_token(token)


# -------------------------------------------------------------------
# 路由：注册 / 登录 / 当前用户 / 改密码
# -------------------------------------------------------------------
@router.post("/register")
def register(payload: RegisterReq, db: Session = Depends(_get_sync_session)):
    svc = UserService(db)
    try:
        user = svc.create_user(payload.username, payload.password, payload.role_id)
        return {"ok": True, "user_id": user.id, "username": user.username, "role_id": user.role_id}
    except DuplicateUserError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
def login(payload: LoginReq, db: Session = Depends(_get_sync_session)):
    svc = UserService(db)
    user = svc.authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = svc.create_token_for_user(user)
    return {"ok": True, "access_token": token, "token_type": "bearer", "username": user.username}


@router.get("/me")
def me(Authorization: Optional[str] = Header(None), db: Session = Depends(_get_sync_session)):
    token = _bearer_token(Authorization)
    svc = UserService(db)
    user = svc.get_user_from_token(token or "")
    if not user:
        raise HTTPException(status_code=401, detail="未认证")
    perms = svc.get_user_permissions(user)
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "role_id": user.role_id,
            "permissions": perms,
        },
    }


@router.post("/change-password")
def change_password(
    payload: ChangePasswordReq,
    Authorization: Optional[str] = Header(None),
    db: Session = Depends(_get_sync_session),
):
    token = _bearer_token(Authorization)
    svc = UserService(db)
    user = svc.get_user_from_token(token or "")
    if not user:
        raise HTTPException(status_code=401, detail="未认证")
    try:
        svc.change_password(user.id, payload.old_password, payload.new_password)
        return {"ok": True}
    except AuthorizationError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------------------------------------------------------------------
# 路由：角色/权限管理（最小必需）
# -------------------------------------------------------------------
@router.post("/users/{user_id}/role")
def assign_role(user_id: int, payload: AssignRoleReq, db: Session = Depends(_get_sync_session)):
    svc = UserService(db)
    try:
        svc.assign_role_to_user(user_id, payload.role_id)
        return {"ok": True}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/roles/{role_id}/permissions")
def add_perm(role_id: int, payload: PermissionReq, db: Session = Depends(_get_sync_session)):
    svc = UserService(db)
    try:
        svc.add_permission_to_role(role_id, payload.permission)
        return {"ok": True}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/roles/{role_id}/permissions/{permission}")
def del_perm(role_id: int, permission: str, db: Session = Depends(_get_sync_session)):
    svc = UserService(db)
    try:
        svc.remove_permission_from_role(role_id, permission)
        return {"ok": True}
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
