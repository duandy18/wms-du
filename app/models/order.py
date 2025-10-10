from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

OrderType = ("SALES", "PURCHASE")
OrderStatus = ("DRAFT", "CONFIRMED", "FULFILLED", "CANCELED")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    order_type: Mapped[str] = mapped_column(Enum(*OrderType, name="order_type"), index=True)
    status: Mapped[str] = mapped_column(Enum(*OrderStatus, name="order_status"), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="CURRENT_TIMESTAMP"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="CURRENT_TIMESTAMP"
    )

    lines: Mapped[list[OrderItem]] = relationship(back_populates="order", cascade="all, delete")
