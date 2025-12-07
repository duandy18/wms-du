# app/models/permission.py
from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.role import role_permissions  # 关联表对象


class Permission(Base):
    """
    权限模型，对应 permissions 表。

    字段：
    - id: 主键
    - name: 权限名（如 'config.store.write'），全局唯一
    """

    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # unique=True 已经隐含索引，这里不再声明 index=True
    name = Column(String(128), nullable=False, unique=True)

    # 多对多：有哪些角色拥有该权限
    roles = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Permission id={self.id} name={self.name!r}>"
