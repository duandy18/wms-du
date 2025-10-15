# app/models/warehouse.py
from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base


class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)

    # 只保留“有外键”的关系：
    # locations.warehouse_id -> warehouses.id
    locations = relationship(
        "Location",
        back_populates="warehouse",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # 注意：batches 表当前没有 warehouse_id 外键，
    # 所以不要声明下面这个关系，否则会触发 NoForeignKeysError。
    # batches = relationship("Batch", back_populates="warehouse")  # ❌ 禁用
