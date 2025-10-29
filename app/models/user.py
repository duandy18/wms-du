# app/models/user.py
from __future__ import annotations

from typing import List

from sqlalchemy import Boolean, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
# 关键：导入关联表，避免循环依赖问题
from app.models.associations import user_role


class User(Base):
    """
    用户模型（强契约·不改表结构）
    字段保持与现有表一致：
      - id: 主键（String）
      - full_name: 可空
      - email: 唯一 & 非空
      - hashed_password: 非空
      - is_active: 默认 True
      - is_superuser: 默认 False
    关系：
      - roles: 多对多 -> Role（通过 user_role 中间表）
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_full_name", "full_name"),
    )

    # 主键（String），沿用现有类型
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 基本信息
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 多对多：User <-> Role
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=user_role,
        back_populates="users",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id!r} email={self.email!r} active={self.is_active} super={self.is_superuser}>"
