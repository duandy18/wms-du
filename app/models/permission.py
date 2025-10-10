# app/models/permission.py

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.associations import role_permission  # ← 关键


class Permission(Base):
    """
    权限模型，定义了具体的系统权限。
    """

    __tablename__ = "permissions"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)

    # 关系：一个权限可以被多个角色拥有
    roles = relationship("Role", secondary=role_permission, back_populates="permissions")
