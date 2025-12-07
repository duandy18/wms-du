from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .item import Item
    from .order import Order


class OrderItem(Base):
    __tablename__ = "order_items"
    __allow_unmapped__ = True

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )

    sku_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    shipped_qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    returned_qty: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    extras: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="order_items",
        lazy="selectin",
    )
    item: Mapped["Item"] = relationship(
        "Item",
        back_populates="order_items",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<OrderItem id={self.id} order_id={self.order_id} "
            f"item_id={self.item_id} qty={self.qty} "
            f"shipped={self.shipped_qty} returned={self.returned_qty}>"
        )
