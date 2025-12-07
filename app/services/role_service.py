# app/services/role_service.py
from __future__ import annotations

from typing import Iterable, List, Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert  # ⭐ 关键：PostgreSQL insert
from sqlalchemy.orm import Session

from app.models.permission import Permission
from app.models.role import Role, role_permissions


class RoleService:
    """
    角色服务：负责角色的增删查，以及与权限的绑定。

    目前提供能力：
    - create_role(name, description)
    - get_all_roles()
    - get_role_by_id(role_id)
    - add_permissions_to_role(role_id, permission_ids)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ----------------------- 基础查询 -----------------------

    def _ensure_role(self, role_id: int) -> Role:
        role = self.db.get(Role, role_id)
        if not role:
            raise ValueError(f"Role id={role_id} not found")
        return role

    def _ensure_permissions(self, ids: Iterable[int]) -> List[Permission]:
        ids = list(ids)
        if not ids:
            return []
        perms = (
            self.db.query(Permission).filter(Permission.id.in_(ids)).order_by(Permission.id).all()
        )
        if len(perms) != len(ids):
            existing_ids = {p.id for p in perms}
            missing = [i for i in ids if i not in existing_ids]
            raise ValueError(f"Permissions not found: {missing}")
        return perms

    # ----------------------- 角色 CRUD -----------------------

    def create_role(self, name: str, description: Optional[str] = None) -> Role:
        name = (name or "").strip()
        if not name:
            raise ValueError("role name cannot be empty")

        # 检查重名
        existing = self.db.query(Role).filter(Role.name == name).first()
        if existing is not None:
            raise ValueError(f"role {name!r} already exists")

        role = Role(name=name, description=description)
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    def get_all_roles(self) -> List[Role]:
        return self.db.query(Role).order_by(Role.id).all()

    def get_role_by_id(self, role_id: str | int) -> Optional[Role]:
        try:
            rid = int(role_id)
        except (TypeError, ValueError):
            return None
        return self.db.get(Role, rid)

    # ----------------------- 权限绑定 -----------------------

    def add_permissions_to_role(
        self,
        role_id: str | int,
        permission_ids: List[str],
    ) -> Role:
        """
        为给定角色绑定一组权限（幂等）：

        - role_id: 角色 ID（字符串或整数）
        - permission_ids: 权限 ID 列表（字符串或整数）

        行为：
        - 若角色不存在 → ValueError
        - 若任一权限不存在 → ValueError
        - 已经存在的 (role_id, permission_id) 绑定不会重复插入（ON CONFLICT DO NOTHING）
        - 成功后返回最新的 Role 实体
        """
        # 解析角色 ID
        try:
            rid = int(role_id)
        except (TypeError, ValueError):
            raise ValueError(f"invalid role_id={role_id!r}")

        role = self._ensure_role(rid)

        # 解析权限 ID
        try:
            pid_ints = [int(x) for x in (permission_ids or [])]
        except (TypeError, ValueError):
            raise ValueError(f"invalid permission_ids={permission_ids!r}")

        # 确认所有权限存在（若缺失则抛错）
        self._ensure_permissions(pid_ints)

        # 使用 PostgreSQL 的 INSERT ... ON CONFLICT DO NOTHING 做幂等插入
        for pid in pid_ints:
            stmt = (
                pg_insert(role_permissions)
                .values(role_id=rid, permission_id=pid)
                .on_conflict_do_nothing()
            )
            self.db.execute(stmt)

        self.db.commit()
        # 刷新 role，保证关联关系（permissions）是最新的
        self.db.refresh(role)
        return role
