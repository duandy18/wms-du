from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.models.associations import role_permission


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)

    roles = relationship("Role", secondary=role_permission, back_populates="permissions")
