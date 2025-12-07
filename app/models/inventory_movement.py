from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        Index("ix_inventory_movements_id", "id"),
        Index("ix_inventory_movements_item_sku", "item_sku"),
        Index("ix_inventory_movements_movement_type", "movement_type"),
        Index("ix_inventory_movements_sku_time", "item_sku", "timestamp"),
        Index("ix_inventory_movements_type_time", "movement_type", "timestamp"),
        {"extend_existing": True},  # 防止重复定义报错
    )

    # ---- 主键 TEXT，与数据库一致 ----
    id: Mapped[str] = mapped_column(Text, primary_key=True)

    # ---- 基础字段 ----
    item_sku: Mapped[Optional[str]] = mapped_column(String, ForeignKey("items.sku"), nullable=True)
    from_location_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    to_location_id: Mapped[Optional[int]] = mapped_column(ForeignKey("locations.id"), nullable=True)

    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    movement_type: Mapped[str] = mapped_column(
        SAEnum("RECEIPT", "SHIPMENT", "TRANSFER", "ADJUSTMENT", name="movementtype"),
        nullable=False,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
