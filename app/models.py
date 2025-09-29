# app/models.py
# =========================================================
# 统一的 SQLAlchemy 2.x 风格模型文件（含 User + RBAC）
# - 提供 metadata 以便 Alembic 从 app.models 导入
# - 提供 User / Role / Permission 及关联关系
# - 类型注解全部使用 Mapped[...] 形式
# =========================================================
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Table,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

# 你的项目里应当在 app/db.py 定义了 Base/engine/SessionLocal 等
# 这里仅导入 Base；metadata 别名在文末导出，供 Alembic 使用
from app.db import Base


# -----------------------------
# User（根据你“init users (with naming)”迁移推断的典型字段）
# 若你的迁移里字段不同，请在此处相应调整（以迁移为准）
# -----------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # RBAC：在文件下方定义 Role 后，会补充 roles 关系（见文末 try/except 段）
    # roles: Mapped[List["Role"]]  # 延后绑定


# -----------------------------
# RBAC 多对多关联表
# -----------------------------
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


# -----------------------------
# RBAC 实体：Role / Permission
# -----------------------------
class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    permissions: Mapped[List["Permission"]] = relationship(
        "Permission", secondary=role_permissions, back_populates="roles"
    )
    users: Mapped[List["User"]] = relationship(
        "User", secondary=user_roles, back_populates="roles"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)  # e.g. "purchase:view"
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    roles: Mapped[List["Role"]] = relationship(
        "Role", secondary=role_permissions, back_populates="permissions"
    )


# -----------------------------
# 让 User.roles 与 Role.users 成对出现（若未定义则补刀）
# -----------------------------
if not hasattr(User, "roles"):
    User.roles = relationship(
        "Role", secondary=user_roles, back_populates="users"
    )


# -----------------------------
# Alembic 入口所需：导出 metadata
# -----------------------------
metadata = Base.metadata

__all__ = [
    "metadata",
    "User",
    "Role",
    "Permission",
    "user_roles",
    "role_permissions",
]
