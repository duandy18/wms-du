# app/models/inventory.py
from __future__ import annotations
import enum
from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class MovementType(enum.Enum):
    RECEIPT = "receipt"       # 收货
    SHIPMENT = "shipment"     # 发货
    TRANSFER = "transfer"     # 库内转移
    ADJUSTMENT = "adjustment" # 库存调整


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(String, primary_key=True, index=True)

    # 物料：用 sku 作为业务主键（items.sku 唯一）
    item_sku = Column(String, ForeignKey("items.sku"), index=True, nullable=False)

    # 库位：整型外键对齐 locations.id
    from_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    to_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)

    quantity = Column(Float, nullable=False)
    movement_type = Column(Enum(MovementType), nullable=False)

    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 关系
    item = relationship("Item", primaryjoin="Item.sku==InventoryMovement.item_sku")
    from_location = relationship("Location", foreign_keys=[from_location_id])
    to_location = relationship("Location", foreign_keys=[to_location_id])
