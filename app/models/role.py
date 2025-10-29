# app/models/role.py
from __future__ import annotations

from typing import List

from sqlalchemy import String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
# 复用既有的关联表，避免循环依赖
from app.models.associations import role_permission, user_role


class Role(Base):
    """
    角色模型（强契约·不改表结构）
    字段：
      - id           主键（字符串）
      - name         名称（唯一，非空）
      - description  描述（可空）
    关系：
      - permissions  多对多 -> Permission（通过 role_permission）
      - users        多对多 -> User       （通过 user_role）
    """

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", name="uq_roles_name"),
        Index("ix_roles_name", "name"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # 多对多关系
    permissions: Mapped[List["Permission"]] = relationship(
        "Permission",
        secondary=role_permission,
        back_populates="roles",
        lazy="selectin",
    )

    users: Mapped[List["User"]] = relationship(
        "User",
        secondary=user_role,
        back_populates="roles",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Role id={self.id!r} name={self.name!r}>"
