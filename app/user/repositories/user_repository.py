# app/user/repositories/user_repository.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.permission import Permission
from app.models.user import User, user_permissions
from app.user.services.user_errors import DuplicateUserError, NotFoundError


class UserRepository:
    """
    用户仓储层：

    仅负责 users / user_permissions 的数据库读写。
    不负责权限判定与业务编排。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # =======================================================
    # 基础查询
    # =======================================================
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        return self.db.query(User).filter(User.username == username).first()

    def list_users(self) -> list[User]:
        return self.db.query(User).order_by(User.id.asc()).all()

    # =======================================================
    # 内部工具：权限 ID 校验 / 归一
    # =======================================================
    def _normalize_permission_ids(self, permission_ids: Optional[List[int]]) -> list[int]:
        if not permission_ids:
            return []

        out: list[int] = []
        seen: set[int] = set()

        for raw in permission_ids:
            pid = int(raw)
            if pid not in seen:
                seen.add(pid)
                out.append(pid)

        return out

    def _ensure_permissions_exist(self, permission_ids: Optional[List[int]]) -> list[int]:
        ids = self._normalize_permission_ids(permission_ids)
        if not ids:
            return []

        perms = self.db.query(Permission).filter(Permission.id.in_(ids)).all()
        existing_ids = {int(p.id) for p in perms}

        missing = [pid for pid in ids if pid not in existing_ids]
        if missing:
            raise NotFoundError(f"权限不存在: {missing}")

        return ids

    def _replace_user_permissions(self, user_id: int, permission_ids: list[int]) -> None:
        self.db.execute(user_permissions.delete().where(user_permissions.c.user_id == user_id))

        for pid in permission_ids:
            self.db.execute(
                user_permissions.insert().values(
                    user_id=user_id,
                    permission_id=pid,
                )
            )

    # =======================================================
    # 用户写操作
    # =======================================================
    def create_user(
        self,
        *,
        username: str,
        password: str,
        permission_ids: Optional[List[int]] = None,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        existed = self.get_user_by_username(username)
        if existed:
            raise DuplicateUserError("用户名已存在")

        normalized_permission_ids = self._ensure_permissions_exist(permission_ids)

        user = User(
            username=username.strip(),
            password_hash=get_password_hash(password),
            full_name=(full_name or "").strip() or None,
            phone=(phone or "").strip() or None,
            email=(email or "").strip() or None,
        )
        self.db.add(user)
        self.db.flush()

        self._replace_user_permissions(int(user.id), normalized_permission_ids)

        self.db.commit()
        self.db.refresh(user)
        self.db.expire(user, ["permissions"])
        return user

    def update_user_profile(
        self,
        *,
        user_id: int,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> User:
        user = self.get_user_by_id(user_id)
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

        self.db.commit()
        self.db.refresh(user)
        return user

    def replace_user_permissions(
        self,
        *,
        user_id: int,
        permission_ids: Optional[List[int]] = None,
    ) -> User:
        user = self.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")

        normalized_permission_ids = self._ensure_permissions_exist(permission_ids)
        self._replace_user_permissions(user_id, normalized_permission_ids)

        self.db.commit()
        self.db.refresh(user)
        self.db.expire(user, ["permissions"])
        return user

    def reset_user_password(self, *, user_id: int, new_password: str) -> User:
        user = self.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")

        user.password_hash = get_password_hash(new_password)
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, *, user_id: int) -> None:
        user = self.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("用户不存在")

        try:
            self.db.delete(user)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ValueError("该用户已被业务单据引用，暂不能删除")


__all__ = ["UserRepository"]
