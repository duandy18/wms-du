from __future__ import annotations
from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Index, Integer,
    UniqueConstraint, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    snapshot_date: Mapped[Date] = mapped_column(Date, index=True, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True, nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True, nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True, nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), index=True, nullable=True)

    qty_on_hand: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0, nullable=False)
    qty_allocated: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0, nullable=False)
    qty_available: Mapped[int] = mapped_column(Integer, server_default=text("0"), default=0, nullable=False)

    expiry_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date", "warehouse_id", "location_id", "item_id", "batch_id",
            name="uq_stock_snapshot_grain",
        ),
        Index("ix_ss_item_date", "item_id", "snapshot_date"),
        Index("ix_ss_wh_date", "warehouse_id", "snapshot_date"),
    )
