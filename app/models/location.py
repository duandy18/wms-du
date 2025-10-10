# app/models/location.py
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)

    # 到仓库
    warehouse = relationship("Warehouse", back_populates="locations")

    # 到现势库存
    stocks = relationship("Stock", back_populates="location")

    # ✅ 新增：到批次（与 Batch.location = relationship(..., back_populates="location") 对应）
    batches = relationship("Batch", back_populates="location")
