# app/models/stock_snapshot.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .item import Item


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(Integer, ForeignKey("warehouses.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=False)
    batch_code: Mapped[str] = mapped_column(String(length=64), nullable=False)

    qty_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )
    qty_allocated: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )
    qty_available: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False, server_default=text("0")
    )

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "warehouse_id",
            "item_id",
            "batch_code",
            name="uq_stock_snapshot_grain_v2",
        ),
        Index("ix_stock_snapshots_item_id", "item_id"),
        Index("ix_stock_snapshots_snapshot_date", "snapshot_date"),
        Index("ix_stock_snapshots_warehouse_id", "warehouse_id"),
        {"info": {"skip_autogen": True}},
    )

    item: Mapped["Item"] = relationship("Item", lazy="selectin")
