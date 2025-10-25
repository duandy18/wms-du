# app/models/user.py
from sqlalchemy import Boolean, Column, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.associations import user_role


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    full_name = Column(String, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)

    roles = relationship("Role", secondary=user_role, back_populates="users")
