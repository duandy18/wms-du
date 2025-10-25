from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)

    # locations.warehouse_id -> warehouses.id
    locations = relationship(
        "Location",
        back_populates="warehouse",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
