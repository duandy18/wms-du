# app/models/permission.py
from __future__ import annotations

from typing import List

from sqlalchemy import String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.associations import role_permission


class Permission(Base):
    """
    权限模型（强契约·现代声明式）：
      - id: 主键
      - name: 唯一、非空
      - description: 可空
      - roles: 多对多 -> Role（通过 role_permission）
    """

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("name", name="uq_permissions_name"),
        Index("ix_permissions_name", "name"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # 关系：一个权限可被多个角色拥有
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=role_permission,
        back_populates="permissions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Permission id={self.id!r} name={self.name!r}>"
