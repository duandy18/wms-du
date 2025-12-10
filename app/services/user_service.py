# app/services/user_service.py

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from app.models.permission import Permission
from app.models.role import Role, role_permissions
from app.models.user import User, user_roles


class AuthorizationError(Exception):
    """权限不足"""


class DuplicateUserError(Exception):
    """用户名已存在"""


class NotFoundError(Exception):
    """实体不存在"""


class UserService:
    """
    多角色 RBAC 版 UserService：
    - 支持 primary_role_id（主角色）
    - 支持 user_roles 多角色
    - 权限 = 所有角色权限并集
    """

    def __init__(self, db_session: Session):
        self.db: Session = db_session

    # =======================================================
    # 用户查询
    # =======================================================
    def get_user_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    # =======================================================
    # 登录认证
    # =======================================================
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        user = self.db.query(User).filter(User.username == username).first()
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    # =======================================================
    # 生成 JWT
    # =======================================================
    def create_token_for_user(self, user: User, *, expires_in: Optional[int] = None) -> str:
        payload = {"sub": user.username}
        return create_access_token(data=payload, expires_minutes=expires_in)

    def get_user_from_token(self, token: str) -> Optional[User]:
        payload = decode_access_token(token)
        if not payload or "sub" not in payload:
            return None
        return self.get_user_by_username(payload["sub"])

    # =======================================================
    # 创建用户（主角色 + 多角色）
    # =======================================================
    def create_user(
        self,
        username: str,
        password: str,
        primary_role_id: int,
        *,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        extra_role_ids: Optional[List[int]] = None,
    ) -> User:

        existed = self.db.query(User).filter(User.username == username).first()
        if existed:
            raise DuplicateUserError("用户名已存在")

        # 主角色必须存在
        primary_role = self.db.query(Role).filter(Role.id == primary_role_id).first()
        if not primary_role:
            raise NotFoundError("主角色不存在")

        # 创建用户
        user = User(
            username=username.strip(),
            password_hash=get_password_hash(password),
            primary_role_id=primary_role_id,
            full_name=(full_name or "").strip() or None,
            phone=(phone or "").strip() or None,
            email=(email or "").strip() or None,
        )
        self.db.add(user)
        self.db.flush()  # 获取 user.id

        # 多角色绑定
        if extra_role_ids:
            for rid in extra_role_ids:
                self.db.execute(
                    user_roles.insert().values(user_id=user.id, role_id=rid)
                )

        self.db.commit()
        self.db.refresh(user)
        return user

    # =======================================================
    # 更新用户（基础信息 + 主角色 + 多角色）
    # =======================================================
    def update_user(
        self,
        user_id: int,
        *,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        primary_role_id: Optional[int] = None,
        extra_role_ids: Optional[List[int]] = None,
        is_active: Optional[bool] = None,
    ) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise NotFoundError("用户不存在")

        if full_name is not None:
            user.full_name = full_name or None
        if phone is not None:
            user.phone = phone or None
        if email is not None:
            user.email = email or None
        if is_active is not None:
            user.is_active = bool(is_active)

        # 更新主角色
        if primary_role_id is not None:
            role = self.db.query(Role).filter(Role.id == primary_role_id).first()
            if not role:
                raise NotFoundError("主角色不存在")
            user.primary_role_id = primary_role_id

        # 更新多角色
        if extra_role_ids is not None:
            # 清空旧数据
            self.db.execute(
                user_roles.delete().where(user_roles.c.user_id == user_id)
            )
            # 插入新数据
            for rid in extra_role_ids:
                self.db.execute(
                    user_roles.insert().values(user_id=user_id, role_id=rid)
                )

        self.db.commit()
        self.db.refresh(user)
        return user

    # =======================================================
    # 密码修改
    # =======================================================
    def change_password(self, user_id: int, old_password: str, new_password: str):
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise NotFoundError("用户不存在")
        if not verify_password(old_password, user.password_hash):
            raise AuthorizationError("旧密码不正确")

        user.password_hash = get_password_hash(new_password)
        self.db.commit()

    # =======================================================
    # 权限查询（并集）
    # =======================================================
    def get_user_permissions(self, user: Any) -> List[str]:
        if not user:
            return []

        role_ids = set()

        # 主角色
        if getattr(user, "primary_role_id", None):
            role_ids.add(int(user.primary_role_id))

        # 多角色
        rows = self.db.execute(
            text("SELECT role_id FROM user_roles WHERE user_id = :uid"),
            {"uid": user.id},
        ).fetchall()
        for (rid,) in rows:
            role_ids.add(int(rid))

        if not role_ids:
            return []

        # 查询所有角色权限（并集）
        rows = (
            self.db.query(Permission.name)
            .join(role_permissions, Permission.id == role_permissions.c.permission_id)
            .filter(role_permissions.c.role_id.in_(role_ids))
            .all()
        )

        out: List[str] = []
        seen = set()

        for (name,) in rows:
            if name not in seen:
                seen.add(name)
                out.append(name)

        return out

    # =======================================================
    # 权限校验
    # =======================================================
    def check_permission(self, user: Any, required: List[str], *, any_of=True):
        perms = set(self.get_user_permissions(user))
        req = set(required)

        if any_of:
            ok = bool(perms & req)
        else:
            ok = req.issubset(perms)

        if not ok:
            raise AuthorizationError("你没有访问该资源的权限")

        return True
