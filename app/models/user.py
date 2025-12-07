# app/models/user.py
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship

from app.db.base import Base

# 关联表：用户 ←→ 角色，多对多
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


class User(Base):
    """
    系统用户，对应 users 表。

    字段：
    - id: 主键
    - username: 登录名，全局唯一
    - password_hash: 密码哈希
    - is_active: 是否启用
    - full_name: 姓名
    - phone: 联系电话
    - email: 邮件地址
    - primary_role_id: 主角色（可选）
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # unique=True 已经隐含索引，这里不再声明 index=True
    username = Column(String(64), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="TRUE")

    # ⭐ 新增三列
    full_name = Column(String(128), nullable=True)
    phone = Column(String(32), nullable=True)
    email = Column(String(255), nullable=True)

    primary_role_id = Column(
        Integer,
        ForeignKey(
            "roles.id",
            name="fk_users_primary_role_id_roles",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # 主角色：简化场景（一个用户一个主角色）
    primary_role = relationship("Role", foreign_keys=[primary_role_id], lazy="joined")

    # 多角色：通过 user_roles 多对多
    roles = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} active={self.is_active}>"
