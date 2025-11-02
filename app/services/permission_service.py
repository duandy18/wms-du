# app/services/permission_service.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.permission import Permission


class PermissionService:
    """
    最小可用的权限服务（同步 Session 版）：
      - create_permission(name)
      - get_all_permissions()
      - get_permission_by_id(id)
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_permission(self, name: str) -> Permission:
        name = (name or "").strip()
        if not name:
            raise ValueError("permission name is required")

        exists = self.db.execute(
            select(Permission).where(Permission.name == name)
        ).scalar_one_or_none()
        if exists:
            raise ValueError(f"Permission '{name}' already exists")

        obj = Permission(name=name)
        self.db.add(obj)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            # 针对并发/唯一约束兜底
            raise ValueError(f"Permission '{name}' already exists") from e
        self.db.refresh(obj)
        return obj

    def get_all_permissions(self) -> List[Permission]:
        rows = self.db.execute(
            select(Permission).order_by(Permission.id.asc())
        ).scalars().all()
        return list(rows)

    def get_permission_by_id(self, permission_id: str | int) -> Optional[Permission]:
        try:
            pid = int(permission_id)
        except Exception:
            return None
        return self.db.execute(
            select(Permission).where(Permission.id == pid)
        ).scalar_one_or_none()
