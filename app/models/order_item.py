# app/models/order_item.py
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.item import Item


class OrderItem(Base):
    """
    订单行项目（强契约·现代声明式）
    与原表结构完全一致：
      - id 主键自增
      - order_id → orders.id（CASCADE 删除）
      - item_id  → items.id（RESTRICT 删除）
      - qty / unit_price / line_amount 均为数值字段
    无需迁移。
    """

    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_order_item", "order_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    line_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # 关系：订单 ↔ 行项目；商品 ↔ 行项目
    order: Mapped["Order"] = relationship("Order", back_populates="lines", lazy="selectin")
    item: Mapped["Item"] = relationship("Item", back_populates="lines", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<OrderItem id={self.id} order_id={self.order_id} "
            f"item_id={self.item_id} qty={self.qty} line_amount={self.line_amount}>"
        )
