# app/services/role_service.py
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from sqlalchemy import select, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.permission import Permission
from app.models.associations import role_permission  # 作为关系表兜底使用


class RoleService:
    """
    最小可用的角色服务（同步 Session 版）：
      - create_role(name, description)
      - get_all_roles()
      - get_role_by_id(id)
      - add_permissions_to_role(role_id, permission_ids)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_role(self, name: str, description: Optional[str] = None) -> Role:
        name = (name or "").strip()
        if not name:
            raise ValueError("role name is required")

        exists = self.db.execute(
            select(Role).where(Role.name == name)
        ).scalar_one_or_none()
        if exists:
            raise ValueError(f"Role '{name}' already exists")

        obj = Role(name=name, description=(description or ""))
        self.db.add(obj)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"Role '{name}' already exists") from e
        self.db.refresh(obj)
        return obj

    def get_all_roles(self) -> List[Role]:
        rows = self.db.execute(
            select(Role).order_by(Role.id.asc())
        ).scalars().all()
        return list(rows)

    def get_role_by_id(self, role_id: str | int) -> Optional[Role]:
        try:
            rid = int(role_id)
        except Exception:
            return None
        return self.db.execute(
            select(Role).where(Role.id == rid)
        ).scalar_one_or_none()

    def add_permissions_to_role(
        self, role_id: int, permission_ids: Sequence[int]
    ) -> Role:
        """
        将一组 permission 绑定到角色上。
        - 优先尝试通过关系属性（若模型里定义了 role.permissions）
        - 若无关系属性，则直接插入关系表 role_permission
        """
        role = self.get_role_by_id(role_id)
        if not role:
            raise ValueError(f"Role id={role_id} not found")

        if not permission_ids:
            return role

        # 拉取所有存在的 Permission
        perms = self.db.execute(
            select(Permission).where(Permission.id.in_(list(permission_ids)))
        ).scalars().all()
        if not perms:
            raise ValueError("No valid permission ids provided")

        # 优先通过 relationship 绑定
        using_relationship = hasattr(role, "permissions") and isinstance(getattr(role, "permissions"), list)
        if using_relationship:
            # 去重：只绑定还没有的
            has_ids = {p.id for p in role.permissions}  # type: ignore[attr-defined]
            to_bind = [p for p in perms if p.id not in has_ids]
            role.permissions.extend(to_bind)  # type: ignore[attr-defined]
            try:
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
            self.db.refresh(role)
            return role

        # 若没有 relationship，直接插 role_permission（兜底）
        existing = self.db.execute(
            select(role_permission.c.permission_id).where(
                (role_permission.c.role_id == role_id)
                & (role_permission.c.permission_id.in_(list(permission_ids)))
            )
        ).scalars().all()
        existing_set = set(int(x) for x in existing)

        to_insert = [
            {"role_id": role_id, "permission_id": int(p.id)}
            for p in perms
            if int(p.id) not in existing_set
        ]
        if to_insert:
            try:
                self.db.execute(insert(role_permission), to_insert)
                self.db.commit()
            except IntegrityError:
                self.db.rollback()

        # 重新查询 role（若你在 Role 模型里无 relationship，这里还是原样返回）
        self.db.refresh(role)
        return role
