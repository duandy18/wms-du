# app/models/inventory.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enum import MovementType  # 统一从集中枚举处导入


class InventoryMovement(Base):
    """
    库存移动流水（保持现有表结构）：
    - 主键：id (String)
    - 维度：item_sku（FK → items.sku）、from_location_id/to_location_id（String FK → locations.id）
    - 指标：quantity (Float)
    - 类型：movement_type (Enum)
    - 时间：timestamp（具时区，DB 默认 UTC via NOW()）
    说明：仅升级为现代声明式写法并补充索引，不触发迁移。
    """

    __tablename__ = "inventory_movements"
    __table_args__ = (
        # 常用检索：按 SKU + 时间线
        Index("ix_inventory_movements_sku_time", "item_sku", "timestamp"),
        Index("ix_inventory_movements_type_time", "movement_type", "timestamp"),
    )

    # 主键
    id: Mapped[str] = mapped_column(String, primary_key=True, index=True)

    # 关联物料和库位（按现有结构保留 String 外键）
    item_sku: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("items.sku", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    from_location_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    to_location_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=True,
    )

    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    movement_type: Mapped[MovementType] = mapped_column(
        SAEnum(MovementType),
        nullable=False,
        index=True,
    )

    # 具时区时间；DB 层默认 NOW()（UTC）
    timestamp: Mapped[Optional[object]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=True,
    )

    # 关系字段（显式指定 foreign_keys，避免歧义）
    item = relationship("Item", lazy="selectin")
    from_location = relationship(
        "Location",
        foreign_keys=[from_location_id],
        lazy="selectin",
    )
    to_location = relationship(
        "Location",
        foreign_keys=[to_location_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<InventoryMovement id={self.id!r} sku={self.item_sku!r} "
            f"type={self.movement_type.value} qty={self.quantity} ts={self.timestamp}>"
        )
