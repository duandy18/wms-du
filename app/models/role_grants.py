# app/models/role_grants.py
from __future__ import annotations

from typing import List

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
# 复用既有的中间表（用户↔角色、角色↔权限）
from app.models.user_role_permission import user_role, role_permission


class Role(Base):
    """
    角色模型（与既有表结构对齐）：
    - 仅声明最小且通用的列：id（PK）、name（可选）
    - 关系：
        users       多对多 -> User     （通过 user_role）
        permissions 多对多 -> Permission（通过 role_permission）
    """
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    # 为了兼容不同历史结构，name 允许为空；如你的表有唯一约束，可在 Alembic 中单独声明
    name: Mapped[str | None] = mapped_column(String, nullable=True)

    users: Mapped[List["User"]] = relationship(
        "User",
        secondary=user_role,
        back_populates="roles",
        lazy="selectin",
    )

    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        secondary=role_permission,
        back_populates="roles",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id!r} name={self.name!r}>"


class Permission(Base):
    """
    权限模型（与既有表结构对齐）：
    - 仅声明最小列：id（PK）、name（可选）
    - 关系：
        roles 多对多 -> Role（通过 role_permission）
    """
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)

    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=role_permission,
        back_populates="permissions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Permission id={self.id!r} name={self.name!r}>"
