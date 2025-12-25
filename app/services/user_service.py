# app/services/user_service.py

from __future__ import annotations


from typing import Any, List, Optional

from app.services.user_errors import AuthorizationError, DuplicateUserError, NotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.user import User

from app.services.user_auth import (
    authenticate_user as _authenticate_user,
    create_token_for_user as _create_token_for_user,
    get_user_from_token as _get_user_from_token,
)
from app.services.user_crud import (
    change_password as _change_password,
    create_user as _create_user,
    update_user as _update_user,
)
from app.services.user_permissions import (
    check_permission as _check_permission,
    get_user_permissions as _get_user_permissions,
)


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
        return _authenticate_user(self.db, username, password)

    # =======================================================
    # 生成 JWT
    # =======================================================
    def create_token_for_user(self, user: User, *, expires_in: Optional[int] = None) -> str:
        return _create_token_for_user(user, expires_in=expires_in)

    def get_user_from_token(self, token: str) -> Optional[User]:
        return _get_user_from_token(self.db, token)

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
        return _create_user(
            self.db,
            username=username,
            password=password,
            primary_role_id=primary_role_id,
            full_name=full_name,
            phone=phone,
            email=email,
            extra_role_ids=extra_role_ids,
        )

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
        return _update_user(
            self.db,
            user_id=user_id,
            full_name=full_name,
            phone=phone,
            email=email,
            primary_role_id=primary_role_id,
            extra_role_ids=extra_role_ids,
            is_active=is_active,
        )

    # =======================================================
    # 密码修改
    # =======================================================
    def change_password(self, user_id: int, old_password: str, new_password: str):
        _change_password(
            self.db, user_id=user_id, old_password=old_password, new_password=new_password
        )

    # =======================================================
    # 权限查询（并集）
    # =======================================================
    def get_user_permissions(self, user: Any) -> List[str]:
        return _get_user_permissions(self.db, user)

    # =======================================================
    # 权限校验
    # =======================================================
    def check_permission(self, user: Any, required: List[str], *, any_of=True):
        return _check_permission(self.db, user, required, any_of=any_of)


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

    async def _pick_default_primary_role_id(self, session: AsyncSession) -> int:
        res = await session.execute(text("SELECT id FROM roles ORDER BY id ASC LIMIT 1"))
        rid = res.scalar()
        if rid is None:
            raise NotFoundError("主角色不存在")
        return int(rid)

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

        primary_role_id = await self._pick_default_primary_role_id(session)

        password_hash = get_password_hash("admin123")

        res_ins = await session.execute(
            text(
                """
                INSERT INTO users (username, password_hash, primary_role_id)
                VALUES (:username, :password_hash, :primary_role_id)
                RETURNING id
                """
            ),
            {
                "username": uname,
                "password_hash": password_hash,
                "primary_role_id": primary_role_id,
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
