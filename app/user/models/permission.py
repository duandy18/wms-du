# app/user/models/permission.py
# Domain move: Permission ORM belongs to user runtime permissions.
from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.user.models.user import user_permissions  # 新用户权限关联


class Permission(Base):
    """
    权限模型，对应 permissions 表。
    """

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, unique=True)

    # 新模型：用户直接拥有的权限
    users = relationship(
        "User",
        secondary=user_permissions,
        back_populates="permissions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Permission id={self.id} name={self.name!r}>"
