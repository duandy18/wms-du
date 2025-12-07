# app/models/role.py
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, Table
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.user import user_roles  # 只导入关联表对象，不导入 User 类

# 关联表：角色 ←→ 权限，多对多
role_permissions: Table = sa.Table(
    "role_permissions",
    Base.metadata,
    sa.Column(
        "role_id",
        sa.Integer,
        sa.ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "permission_id",
        sa.Integer,
        sa.ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Role(Base):
    """
    角色模型，对应 roles 表。

    字段：
    - id: 主键
    - name: 角色名（如 'admin'）
    - description: 描述
    """

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # unique=True 已经隐含索引，这里不再声明 index=True
    name = Column(String(64), nullable=False, unique=True)
    description = Column(String(255), nullable=True)

    # 多对多：用户集合（反向映射 user.roles）
    users = relationship(
        "User",
        secondary=user_roles,
        back_populates="roles",
        lazy="selectin",
    )

    # 多对多：权限集合（反向映射 permission.roles）
    permissions = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id} name={self.name!r}>"
