from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .order import Order


class OrderLogistics(Base):
    __tablename__ = "order_logistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracking_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, server_default=text("now()")
    )

    order: Mapped["Order"] = relationship(
        "Order",
        primaryjoin="foreign(OrderLogistics.order_id) == Order.id",
        back_populates="logistics",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<OrderLogistics id={self.id} order_id={self.order_id} tracking={self.tracking_no!r}>"
        )
