# app/models/role.py

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from app.db.base import Base

# 从新的关联表中导入，以打破循环依赖
from app.models.associations import role_permission, user_role  # ← 关键


class Role(Base):
    """
    角色模型，定义了不同的用户角色。
    """

    __tablename__ = "roles"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)

    # 关系：一个角色可以拥有多个权限
    permissions = relationship("Permission", secondary=role_permission, back_populates="roles")

    # 关系：一个角色可以被多个用户拥有
    users = relationship("User", secondary=user_role, back_populates="roles")
