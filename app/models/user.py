# app/models/user.py

from sqlalchemy import Boolean, Column, String
from sqlalchemy.orm import relationship

from app.db.base import Base

# 导入关联表，以打破循环依赖
from app.models.associations import user_role  # ← 关键


class User(Base):
    """
    用户模型。
    """

    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    full_name = Column(String, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)

    # 关系：一个用户可以有多个角色
    roles = relationship("Role", secondary=user_role, back_populates="users")
