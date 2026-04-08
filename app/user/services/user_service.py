# app/user/services/user_service.py

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.user import User
from app.user.repositories.user_repository import UserRepository
from app.user.services.user_admin_audit import AdminUserAuditService
from app.user.services.user_auth import (
    authenticate_user as _authenticate_user,
    create_token_for_user as _create_token_for_user,
    get_user_from_token as _get_user_from_token,
)
from app.user.services.user_errors import AuthorizationError, DuplicateUserError, NotFoundError
from app.user.services.user_permissions import (
    check_permission as _check_permission,
    get_user_permissions as _get_user_permissions,
)

ADMIN_WRITE_PERMISSION = "page.admin.write"


class UserService:
    """
    用户直配权限版 UserService：

    当前主线：
    - 用户最终权限真相源 = user_permissions
    - 用户管理主流程不再使用 primary_role_id / user_roles
    - 角色相关模型与接口暂保留，仅用于后续历史清理
    """

    def __init__(self, db_session: Session):
        self.db: Session = db_session
        self.repo = UserRepository(db_session)
        self.admin_audit = AdminUserAuditService(db_session)

    # =======================================================
    # 用户查询
    # =======================================================
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        return self.repo.get_user_by_id(user_id)

    def get_user_by_username(self, username: str) -> Optional[User]:
        return self.repo.get_user_by_username(username)

    def list_users(self) -> list[User]:
        return self.repo.list_users()

    # =======================================================
    # 登录认证
    # =======================================================
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        return _authenticate_user(self.db, username, password)

    # =======================================================
    # 生成 JWT
    # =======================================================
    def create_token_for_user(self, user: User, *, expires_in: Optional[int] = None) -> str:
        return _create_token_for_user(user, expires_in=expires_in)

    def get_user_from_token(self, token: str) -> Optional[User]:
        return _get_user_from_token(self.db, token)

    # =======================================================
    # 创建用户（用户直配权限）
    # =======================================================
    def create_user(
        self,
        username: str,
        password: str,
        *,
        permission_ids: Optional[List[int]] = None,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        return self.repo.create_user(
            username=username,
            password=password,
            permission_ids=permission_ids,
            full_name=full_name,
            phone=phone,
            email=email,
        )

    # =======================================================
    # 更新用户（仅基础信息 + 启停用）
    # =======================================================
    def update_user(
        self,
        user_id: int,
        *,
        actor_user_id: int | None = None,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> User:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")

        before_is_active = bool(getattr(user, "is_active", True))
        before_username = str(getattr(user, "username", ""))

        if is_active is False and self._is_active_admin_write_user(user):
            self._ensure_not_last_active_admin_writer(action="停用")

        updated_user = self.repo.update_user_profile(
            user_id=user_id,
            full_name=full_name,
            phone=phone,
            email=email,
            is_active=is_active,
        )

        after_is_active = bool(getattr(updated_user, "is_active", True))
        if (
            actor_user_id is not None
            and is_active is not None
            and before_is_active != after_is_active
        ):
            self.admin_audit.write_user_status_updated(
                actor_user_id=int(actor_user_id),
                target_user_id=int(updated_user.id),
                target_username=str(updated_user.username or before_username),
                before_is_active=before_is_active,
                after_is_active=after_is_active,
            )

        return updated_user

    # =======================================================
    # 删除用户
    # =======================================================
    def delete_user(
        self,
        user_id: int,
        *,
        actor_user_id: int | None = None,
    ) -> None:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")

        before_snapshot = {
            "id": int(user.id),
            "username": str(user.username),
            "is_active": bool(getattr(user, "is_active", True)),
            "full_name": getattr(user, "full_name", None),
            "phone": getattr(user, "phone", None),
            "email": getattr(user, "email", None),
            "permissions": sorted(self.get_user_permissions(user)),
        }

        if self._is_active_admin_write_user(user):
            self._ensure_not_last_active_admin_writer(action="删除")

        self.repo.delete_user(user_id=user_id)

        if actor_user_id is not None:
            self.admin_audit.write_user_deleted(
                actor_user_id=int(actor_user_id),
                target_user_id=int(before_snapshot["id"]),
                target_username=str(before_snapshot["username"]),
                before_snapshot=before_snapshot,
            )

    # =======================================================
    # 覆盖用户直配权限
    # =======================================================
    def set_user_permissions(
        self,
        user_id: int,
        *,
        permission_ids: Optional[List[int]] = None,
    ) -> User:
        return self.repo.replace_user_permissions(
            user_id=user_id,
            permission_ids=permission_ids,
        )

    # =======================================================
    # 管理员重置密码
    # =======================================================
    def reset_user_password(
        self,
        user_id: int,
        *,
        new_password: str = "000000",
        actor_user_id: int | None = None,
    ) -> User:
        updated_user = self.repo.reset_user_password(
            user_id=user_id,
            new_password=new_password,
        )

        if actor_user_id is not None:
            self.admin_audit.write_password_reset(
                actor_user_id=int(actor_user_id),
                target_user_id=int(updated_user.id),
                target_username=str(updated_user.username),
            )

        return updated_user

    # =======================================================
    # 密码修改
    # =======================================================
    def change_password(self, user_id: int, old_password: str, new_password: str):
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")
        if not getattr(user, "password_hash", None):
            raise AuthorizationError("旧密码不正确")

        from app.core.security import verify_password

        if not verify_password(old_password, user.password_hash):
            raise AuthorizationError("旧密码不正确")

        user.password_hash = get_password_hash(new_password)
        self.db.commit()

    # =======================================================
    # 权限查询（user_permissions 真相源）
    # =======================================================
    def get_user_permissions(self, user: Any) -> List[str]:
        return _get_user_permissions(self.db, user)

    # =======================================================
    # 权限校验
    # =======================================================
    def check_permission(self, user: Any, required: List[str], *, any_of=True):
        return _check_permission(self.db, user, required, any_of=any_of)

    def _is_active_admin_write_user(self, user: User) -> bool:
        if not bool(getattr(user, "is_active", True)):
            return False

        permission_names = set(self.get_user_permissions(user))
        return ADMIN_WRITE_PERMISSION in permission_names

    def _ensure_not_last_active_admin_writer(self, *, action: str) -> None:
        count = self.repo.count_active_users_with_permission(ADMIN_WRITE_PERMISSION)
        if count <= 1:
            raise ValueError(f"不能{action}最后一个仍拥有 page.admin.write 的有效用户")


class AsyncUserService:
    """
    最小异步契约服务（仅用于测试）：

    tests/services/test_user_service.py 约定：
    - AsyncUserService() 可无参构造
    - create_user(session=..., username=...) -> int(user_id)
    - get_user(session=..., user_id=...) -> dict (至少含 id/username)

    设计原则：
    - 不替代现有同步 UserService（不影响现有业务调用）
    - 不引入业务语义变化，只满足测试最小契约
    - 使用 SQL 直连以避免引入新的 ORM/依赖耦合
    """

    def __init__(self) -> None:
        pass

    async def create_user(self, *, session: AsyncSession, username: str) -> int:
        uname = (username or "").strip()
        if not uname:
            raise ValueError("username is required")

        res_exist = await session.execute(
            text("SELECT id FROM users WHERE username = :u LIMIT 1"),
            {"u": uname},
        )
        existed_id = res_exist.scalar()
        if existed_id is not None:
            raise DuplicateUserError("用户名已存在")

        password_hash = get_password_hash("admin123")

        res_ins = await session.execute(
            text(
                """
                INSERT INTO users (username, password_hash)
                VALUES (:username, :password_hash)
                RETURNING id
                """
            ),
            {
                "username": uname,
                "password_hash": password_hash,
            },
        )
        new_id = res_ins.scalar()
        await session.commit()

        if new_id is None:
            raise NotFoundError("用户不存在")

        return int(new_id)

    async def get_user(self, *, session: AsyncSession, user_id: int) -> Optional[dict[str, Any]]:
        res = await session.execute(
            text("SELECT id, username FROM users WHERE id = :id LIMIT 1"),
            {"id": int(user_id)},
        )
        row = res.mappings().first()
        if not row:
            return None
        return {"id": int(row["id"]), "username": str(row["username"])}


__all__ = [
    "AuthorizationError",
    "DuplicateUserError",
    "NotFoundError",
    "UserService",
    "AsyncUserService",
]
