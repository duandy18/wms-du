# app/models/stock_snapshot.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .item import Item


class StockSnapshot(Base):
    __tablename__ = "stock_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    scope: Mapped[str] = mapped_column(
        sa.Enum("PROD", "DRILL", name="biz_scope"),
        nullable=False,
        index=True,
    )

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(Integer, ForeignKey("warehouses.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey("items.id"), nullable=False)

    # ✅ v2：允许 NULL 表达“无批次”
    batch_code: Mapped[str | None] = mapped_column(String(length=64), nullable=True)

    # ✅ 生成列：把 NULL 映射为稳定 sentinel，用于唯一性/对齐 joins
    batch_code_key: Mapped[str] = mapped_column(
        sa.String(64),
        sa.Computed("coalesce(batch_code, '__NULL_BATCH__')", persisted=True),
        nullable=False,
        index=True,
    )

    # ✅ Stage C.2 最终态：snapshot 事实列为 qty（彻底删除 qty_on_hand）
    qty: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))

    qty_allocated: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))
    qty_available: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, server_default=text("0"))

    __table_args__ = (
        # ✅ 唯一性改为 batch_code_key（保持约束名不变，便于 ON CONFLICT ON CONSTRAINT）
        UniqueConstraint(
            "scope",
            "snapshot_date",
            "warehouse_id",
            "item_id",
            "batch_code_key",
            name="uq_stock_snapshot_grain_v2",
        ),
        Index("ix_stock_snapshots_item_id", "item_id"),
        Index("ix_stock_snapshots_snapshot_date", "snapshot_date"),
        Index("ix_stock_snapshots_warehouse_id", "warehouse_id"),
        Index("ix_stock_snapshots_scope_date", "scope", "snapshot_date"),
        {"info": {"skip_autogen": True}},
    )

    item: Mapped["Item"] = relationship("Item", lazy="selectin")
