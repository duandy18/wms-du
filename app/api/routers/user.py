# app/api/routers/user.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import get_password_hash  # 重置密码需要
from app.db.session import get_db
from app.models.user import User  # 直接使用 User 模型查询列表
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserLogin, UserOut
from app.services.user_service import (
    AuthorizationError,
    DuplicateUserError,
    NotFoundError,
    UserService,
)

router = APIRouter(prefix="/users", tags=["users"])


# ==========================================================
# 内联 Schema
# ==========================================================


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    role_id: int | None = None
    is_active: bool | None = None


class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str


class PasswordResetIn(BaseModel):
    # 如将来需要扩展，可在此加入 extra 字段
    pass


# ==========================================================
# 创建用户
# ==========================================================
@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    注册新用户并分配主角色。

    行为：
    - 需要权限: create_user
    - 用户名已存在 → 400
    - 角色不存在 → 400
    - 其他异常 → 500
    """
    svc = UserService(db)
    try:
        # RBAC：只有具备 create_user 权限的用户才能创建新用户
        svc.check_permission(current_user, ["create_user"])

        user = svc.create_user(
            username=user_in.username,
            password=user_in.password,
            role_id=user_in.role_id,
            # 把姓名 / 电话 / 邮箱一并传给服务层
            full_name=getattr(user_in, "full_name", None),
            phone=getattr(user_in, "phone", None),
            email=getattr(user_in, "email", None),
        )
        return UserOut(
            id=user.id,
            username=user.username,
            role_id=user.primary_role_id,
            is_active=user.is_active,
            full_name=getattr(user, "full_name", None),
            phone=getattr(user, "phone", None),
            email=getattr(user, "email", None),
        )
    except AuthorizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create user",
        )
    except DuplicateUserError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # 这里给出可读错误信息，其它细节在日志里看
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register user: {e}",
        )


# ==========================================================
# 登录
# ==========================================================
@router.post("/login", response_model=Token)
def login(
    user_in: UserLogin,
    db: Session = Depends(get_db),
):
    """
    用户登录，返回访问令牌（JWT）。

    行为：
    - 用户名或密码错误 → 401
    """
    svc = UserService(db)
    try:
        user = svc.authenticate_user(user_in.username, user_in.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        token = svc.create_token_for_user(user)
        # expires_in 暂时用 None（避免破坏现有前端逻辑）
        return Token(access_token=token, token_type="bearer", expires_in=None)
    except HTTPException:
        # 透传上面的 401
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to login: {e}",
        )


# ==========================================================
# 用户列表
# ==========================================================
@router.get("/", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    返回所有用户列表。

    需要权限: read_users 或 read_roles 其一。
    """
    svc = UserService(db)
    try:
        # 允许具备 read_roles 的角色访问用户列表
        svc.check_permission(current_user, ["read_users", "read_roles"])
    except AuthorizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to list users",
        )

    users = db.query(User).all()

    return [
        UserOut(
            id=u.id,
            username=u.username,
            role_id=getattr(u, "primary_role_id", None),
            is_active=u.is_active,
            full_name=getattr(u, "full_name", None),
            phone=getattr(u, "phone", None),
            email=getattr(u, "email", None),
        )
        for u in users
    ]


# ==========================================================
# 更新用户信息 / 启用停用
# ==========================================================
@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    更新用户的基础信息（姓名/电话/邮箱/角色/启用状态）。

    需要权限: update_user 或 create_user 其一。
    """
    svc = UserService(db)

    try:
        # 允许具备 update_user 或 create_user 权限的用户更新资料
        svc.check_permission(current_user, ["update_user", "create_user"])
    except AuthorizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update user",
        )

    try:
        user = svc.update_user(
            user_id=user_id,
            full_name=body.full_name,
            phone=body.phone,
            email=body.email,
            role_id=body.role_id,
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"更新用户失败: {e}",
        )


# ==========================================================
# /users/me：当前用户信息 + 权限
# ==========================================================
@router.get("/me")
def get_me(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    返回当前登录用户的基本信息 + 权限列表。
    """
    svc = UserService(db)
    permissions = svc.get_user_permissions(current_user)

    return {
        "id": getattr(current_user, "id", None),
        "username": getattr(current_user, "username", ""),
        "role_id": getattr(
            current_user,
            "primary_role_id",
            getattr(current_user, "role_id", None),
        ),
        "permissions": permissions,
    }


# ==========================================================
# 登录用户自助修改密码
# ==========================================================
@router.post("/change-password")
def change_password(
    body: PasswordChangeIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    登录用户修改自己的密码。

    不需要额外权限，只要登录。
    """
    svc = UserService(db)
    try:
        svc.change_password(
            user_id=current_user.id,
            old_password=body.old_password,
            new_password=body.new_password,
        )
        return {"ok": True}
    except AuthorizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="旧密码错误",
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"修改密码失败: {e}",
        )


# ==========================================================
# 管理员重置用户密码为默认 000000
# ==========================================================
@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    body: PasswordResetIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    管理员重置用户密码为“000000”。

    需要权限：reset_user_password
    """
    svc = UserService(db)

    # 权限检查
    try:
        svc.check_permission(current_user, ["reset_user_password"])
    except AuthorizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to reset password",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    try:
        user.password_hash = get_password_hash("000000")
        db.commit()
        return {"ok": True, "message": "密码已重置为默认密码 000000"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"重置密码失败: {e}",
        )
