import enum

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class MovementType(enum.Enum):
    RECEIPT = "receipt"  # 收货
    SHIPMENT = "shipment"  # 发货
    TRANSFER = "transfer"  # 库内转移
    ADJUSTMENT = "adjustment"  # 库存调整


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(String, primary_key=True, index=True)

    # 关联物料和库位
    item_sku = Column(String, ForeignKey("items.sku"), index=True)
    from_location_id = Column(String, ForeignKey("locations.id"), nullable=True)
    to_location_id = Column(String, ForeignKey("locations.id"), nullable=True)

    quantity = Column(Float, nullable=False)
    movement_type = Column(Enum(MovementType), nullable=False)

    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # 关系字段，用于快速访问关联对象
    item = relationship("Item")
    from_location = relationship("Location", foreign_keys=[from_location_id])
    to_location = relationship("Location", foreign_keys=[to_location_id])
