# app/models/stock_snapshot.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Date, Index, Integer, Numeric, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.pms.items.models.item import Item


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("warehouses.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, sa.ForeignKey("items.id"), nullable=False)

    # Phase 3: lot-world grain
    lot_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # snapshot facts
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    qty_allocated: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    qty_available: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))

    __table_args__ = (
        # lock lot dims consistency (composite FK)
        sa.ForeignKeyConstraint(
            ["lot_id", "warehouse_id", "item_id"],
            ["lots.id", "lots.warehouse_id", "lots.item_id"],
            name="fk_stock_snapshots_lot_dims",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "snapshot_date",
            "warehouse_id",
            "item_id",
            "lot_id",
            name="uq_stock_snapshots_grain_lot",
        ),
        Index("ix_stock_snapshots_item_id", "item_id"),
        Index("ix_stock_snapshots_snapshot_date", "snapshot_date"),
        Index("ix_stock_snapshots_warehouse_id", "warehouse_id"),
        Index("ix_stock_snapshots_lot_id", "lot_id"),
        Index("ix_stock_snapshots_wh_item_lot", "warehouse_id", "item_id", "lot_id"),
        {"info": {"skip_autogen": True}},
    )

    item: Mapped["Item"] = relationship("Item", lazy="selectin")
