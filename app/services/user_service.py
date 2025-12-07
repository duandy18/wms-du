from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import exc
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from app.models.permission import Permission
from app.models.role import Role, role_permissions
from app.models.user import User


class AuthorizationError(Exception):
    """权限不足"""


class DuplicateUserError(Exception):
    """用户名已存在"""


class NotFoundError(Exception):
    """实体不存在"""


class UserService:
    """
    正式版用户服务（与当前 ORM / RBAC 对齐）：
    - User.password_hash / primary_role_id / full_name / phone / email / is_active
    - 角色权限通过 role_permissions 中间表解析
    """

    def __init__(self, db_session: Session):
        self.db: Session = db_session

    # ------------------------------------------------------------------
    # 用户基本查询
    # ------------------------------------------------------------------

    def get_user_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    # ------------------------------------------------------------------
    # 注册 / 认证
    # ------------------------------------------------------------------

    def create_user(
        self,
        username: str,
        password: str,
        role_id: int,
        *,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        """
        创建新用户并分配主角色。

        可选字段：
        - full_name: 姓名
        - phone: 联系电话
        - email: 邮件地址
        """
        try:
            existed = self.db.query(User).filter(User.username == username).first()
            if existed:
                raise DuplicateUserError("用户名已存在")

            role = self.db.query(Role).filter(Role.id == role_id).first()
            if not role:
                raise NotFoundError("角色不存在")

            user = User(
                username=username.strip(),
                password_hash=get_password_hash(password),
                primary_role_id=role_id,
                full_name=(full_name or "").strip() or None,
                phone=(phone or "").strip() or None,
                email=(email or "").strip() or None,
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            return user

        except (DuplicateUserError, NotFoundError):
            self.db.rollback()
            raise
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            raise e

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        校验用户名 + 密码，成功返回 User，失败返回 None。
        """
        user = self.db.query(User).filter(User.username == username).first()
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    # ------------------------------------------------------------------
    # 修改密码
    # ------------------------------------------------------------------

    def change_password(
        self,
        user_id: int,
        old_password: str,
        new_password: str,
    ) -> None:
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise NotFoundError("用户不存在")
            if not verify_password(old_password, user.password_hash):
                raise AuthorizationError("旧密码不正确")

            user.password_hash = get_password_hash(new_password)
            self.db.commit()
        except (NotFoundError, AuthorizationError):
            self.db.rollback()
            raise
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            raise e

    # ------------------------------------------------------------------
    # 更新用户资料 / 启用停用 / 修改主角色
    # ------------------------------------------------------------------

    def update_user(
        self,
        user_id: int,
        *,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        role_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> User:
        try:
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                raise NotFoundError("用户不存在")

            if full_name is not None:
                user.full_name = (full_name or "").strip() or None
            if phone is not None:
                user.phone = (phone or "").strip() or None
            if email is not None:
                user.email = (email or "").strip() or None

            if role_id is not None:
                role = self.db.query(Role).filter(Role.id == role_id).first()
                if not role:
                    raise NotFoundError("角色不存在")
                user.primary_role_id = role_id

            if is_active is not None:
                user.is_active = bool(is_active)

            self.db.commit()
            self.db.refresh(user)
            return user
        except (NotFoundError,) as e:
            self.db.rollback()
            raise e
        except exc.SQLAlchemyError as e:
            self.db.rollback()
            raise e

    # ------------------------------------------------------------------
    # Token
    # ------------------------------------------------------------------

    def create_token_for_user(
        self,
        user: User,
        *,
        expires_in: Optional[int] = None,
    ) -> str:
        data = {"sub": user.username}
        return create_access_token(data=data, expires_minutes=expires_in)

    def get_user_from_token(self, token: str) -> Optional[User]:
        payload = decode_access_token(token)
        if not payload or "sub" not in payload:
            return None
        username = payload["sub"]
        return self.get_user_by_username(username)

    # ------------------------------------------------------------------
    # 权限
    # ------------------------------------------------------------------

    def get_user_permissions(self, user: Any) -> List[str]:
        """
        从用户主角色解析权限列表（去重）。

        - 对于正常 ORM User：使用 primary_role_id。
        - 对于测试桩 / 匿名用户（如 _TestUser）：若无 primary_role_id/role_id，
          则视为“无权限”，返回空列表，而不是抛 AttributeError。
        """
        if not user:
            return []

        # 正式用户：primary_role_id
        role_id: Optional[int] = getattr(user, "primary_role_id", None)
        # 某些 stub（如 _TestUser）可能用 role_id 字段
        if not role_id:
            role_id = getattr(user, "role_id", None)

        if not role_id:
            return []

        rows = (
            self.db.query(Permission.name)
            .join(role_permissions, Permission.id == role_permissions.c.permission_id)
            .filter(role_permissions.c.role_id == role_id)
            .all()
        )

        out: List[str] = []
        seen = set()
        for (name,) in rows:
            if name not in seen:
                seen.add(name)
                out.append(name)
        return out

    def check_permission(
        self,
        user: Any,
        required_permissions: List[str],
        *,
        any_of: bool = True,
    ) -> bool:
        perms = set(self.get_user_permissions(user))
        req = set(required_permissions or [])
        if not req:
            return True
        ok = (len(perms & req) > 0) if any_of else (req.issubset(perms))
        if not ok:
            raise AuthorizationError("你没有访问该资源的权限")
        return True
