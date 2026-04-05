# app/models/user.py
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from app.db.base import Base

# 关联表：用户 ←→ 角色，多对多（旧模型，暂保留用于历史迁移/清理）
user_roles: Table = sa.Table(
    "user_roles",
    Base.metadata,
    sa.Column(
        "user_id",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "role_id",
        sa.Integer,
        sa.ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

# 关联表：用户 ←→ 权限，多对多（新真身）
user_permissions: Table = sa.Table(
    "user_permissions",
    Base.metadata,
    sa.Column(
        "user_id",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "permission_id",
        sa.Integer,
        sa.ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "granted_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
)


class User(Base):
    """
    系统用户，对应 users 表。

    当前主线：
    - 用户最终权限真相源 = user_permissions
    - primary_role_id / user_roles 仅临时保留用于历史迁移清理
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="TRUE")

    full_name = Column(String(128), nullable=True)
    phone = Column(String(32), nullable=True)
    email = Column(String(255), nullable=True)

    # 旧角色字段：暂保留，不再作为正式权限真相源
    primary_role_id = Column(
        Integer,
        ForeignKey(
            "roles.id",
            name="fk_users_primary_role_id_roles",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    primary_role = relationship("Role", foreign_keys=[primary_role_id], lazy="joined")

    roles = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )

    # 新真身：用户直配权限
    permissions = relationship(
        "Permission",
        secondary=user_permissions,
        back_populates="users",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} active={self.is_active}>"
