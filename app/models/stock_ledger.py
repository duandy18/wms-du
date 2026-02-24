# app/models/stock_ledger.py
from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class StockLedger(Base):
    """
    台账（只增不改）

    Phase 3:
    - 新增 lot_id（影子维度）

    Phase 4A-1:
    - 新增 lot_id_key = COALESCE(lot_id, 0)（generated stored in DB）
    - 幂等唯一键升级为 lot_id_key + batch_code_key 复合键
    """

    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    warehouse_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)

    batch_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True, index=True)

    # ---------------------------
    # Phase 3+: Shadow lot dimension
    # ---------------------------
    lot_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("lots.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Phase 4A-1: generated stored column in DB
    lot_id_key: Mapped[int] = mapped_column(
        sa.Integer,
        sa.Computed("coalesce(lot_id, 0)", persisted=True),
        nullable=False,
        index=True,
    )

    batch_code_key: Mapped[str] = mapped_column(
        sa.String(64),
        sa.Computed("coalesce(batch_code, '__NULL_BATCH__')", persisted=True),
        nullable=False,
        index=True,
    )

    reason: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    reason_canon: Mapped[str | None] = mapped_column(sa.String(32), nullable=True, index=True)

    sub_reason: Mapped[str | None] = mapped_column(sa.String(32), nullable=True, index=True)

    ref: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    ref_line: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)

    delta: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    after_qty: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    occurred_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), server_default=func.now(), nullable=False)

    trace_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    production_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)

    __table_args__ = (
        sa.UniqueConstraint(
            "reason",
            "ref",
            "ref_line",
            "item_id",
            "warehouse_id",
            "lot_id_key",
            "batch_code_key",
            name="uq_ledger_wh_lot_batch_item_reason_ref_line",
        ),
        sa.Index("ix_ledger_dims", "item_id", "batch_code", "warehouse_id"),
        sa.Index("ix_ledger_occurred_at", "occurred_at"),
        sa.Index("ix_stock_ledger_trace_id", "trace_id"),
        sa.Index("ix_stock_ledger_sub_reason_time", "sub_reason", "occurred_at"),
        sa.Index("ix_stock_ledger_reason_canon_time", "reason_canon", "occurred_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Ledger {self.reason}/{self.reason_canon}/{self.sub_reason} "
            f"wh={self.warehouse_id} item={self.item_id} "
            f"code={self.batch_code} lot={self.lot_id} "
            f"delta={self.delta} after={self.after_qty} "
            f"prod={self.production_date} exp={self.expiry_date} "
            f"trace_id={self.trace_id}>"
        )
