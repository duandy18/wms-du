# app/models/associations.py
from sqlalchemy import ForeignKey, Table
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

# 用户 ↔ 角色 多对多
user_role = Table(
    "user_roles",
    Base.metadata,
    mapped_column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    mapped_column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

# 角色 ↔ 权限 多对多
role_permission = Table(
    "role_permissions",
    Base.metadata,
    mapped_column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    mapped_column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)
