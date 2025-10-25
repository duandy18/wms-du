# app/models/role.py
from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.associations import role_permission, user_role  # 统一关联表


class Role(Base):
    __tablename__ = "roles"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)

    # 多对多
    permissions = relationship("Permission", secondary=role_permission, back_populates="roles")
    users = relationship("User", secondary=user_role, back_populates="roles")
