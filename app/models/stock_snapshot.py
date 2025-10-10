from __future__ import annotations

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[Date] = mapped_column(Date, index=True)

    warehouse_id: Mapped[int] = mapped_column(ForeignKey("warehouses.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id"), index=True, nullable=True
    )

    qty_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    qty_allocated: Mapped[int] = mapped_column(Integer, default=0)
    qty_available: Mapped[int] = mapped_column(Integer, default=0)

    expiry_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "warehouse_id",
            "location_id",
            "item_id",
            "batch_id",
            name="uq_stock_snapshot_grain",
        ),
    )
