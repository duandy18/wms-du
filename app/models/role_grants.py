# app/models/user_role_permission.py

from sqlalchemy import Column, ForeignKey, String, Table

from app.db.base import Base

# 多对多关联表：用户和角色
user_role = Table(
    "user_role",
    Base.metadata,
    Column("user_id", String, ForeignKey("users.id"), primary_key=True),
    Column("role_id", String, ForeignKey("roles.id"), primary_key=True),
)

# 多对多关联表：角色和权限
role_permission = Table(
    "role_permission",
    Base.metadata,
    Column("role_id", String, ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", String, ForeignKey("permissions.id"), primary_key=True),
)
