from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, Enum, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

OrderType = ("SALES", "PURCHASE")
OrderStatus = ("DRAFT", "CONFIRMED", "FULFILLED", "CANCELED")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    order_type: Mapped[str] = mapped_column(Enum(*OrderType, name="order_type"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(Enum(*OrderStatus, name="order_status"), index=True, nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(255))
    supplier_name: Mapped[str | None] = mapped_column(String(255))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    lines: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
