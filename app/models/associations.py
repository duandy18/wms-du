# app/models/associations.py
from __future__ import annotations

from sqlalchemy import Table, Column, Integer, ForeignKey, UniqueConstraint

# 你的项目里 Declarative Base 一般在 app/db/base.py 或 app/db/session.py 暴露 Base/metadata
# 这里按常见位置从 base 导入 Base，如果你在 session.py 暴露了 Base/metadata，可改为 from app.db.session import Base
from app.db.base import Base  # 确保 Base.metadata 可用


# 用户-角色 关联（多对多）
user_role = Table(
    "user_role",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("user_id", "role_id", name="uq_user_role_user_role"),
)

# 角色-权限 关联（多对多）
role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("role_id", "permission_id", name="uq_role_permission_role_perm"),
)
