# app/models/warehouse.py
from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)

    # 到库位
    locations = relationship("Location", back_populates="warehouse")

    # ✅ 新增：到批次（与 Batch.warehouse = relationship(..., back_populates="warehouse") 对应）
    batches = relationship("Batch", back_populates="warehouse")
