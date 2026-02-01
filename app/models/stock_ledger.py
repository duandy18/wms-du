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

    ✅ 无批次槽位支持：
    - batch_code 允许为 NULL（表示“无批次”，不是“未知批次”）
    - batch_code_key 为生成列：COALESCE(batch_code,'__NULL_BATCH__')
      并参与幂等唯一约束 uq_ledger_wh_batch_item_reason_ref_line
    """

    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    warehouse_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)

    batch_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True, index=True)

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
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trace_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    production_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)

    __table_args__ = (
        sa.UniqueConstraint(
            "reason",
            "ref",
            "ref_line",
            "item_id",
            "batch_code_key",
            "warehouse_id",
            name="uq_ledger_wh_batch_item_reason_ref_line",
        ),
        sa.Index("ix_ledger_dims", "item_id", "batch_code", "warehouse_id"),
        sa.Index("ix_ledger_occurred_at", "occurred_at"),
        sa.Index("ix_stock_ledger_trace_id", "trace_id"),
        sa.Index("ix_stock_ledger_sub_reason_time", "sub_reason", "occurred_at"),
        sa.Index("ix_stock_ledger_reason_canon_time", "reason_canon", "occurred_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Ledger {self.reason}/{self.reason_canon}/{self.sub_reason} wh={self.warehouse_id} "
            f"item={self.item_id} code={self.batch_code} delta={self.delta} after={self.after_qty} "
            f"prod={self.production_date} exp={self.expiry_date} trace_id={self.trace_id}>"
        )
