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
    幂等唯一： (reason, ref, ref_line, item_id, batch_code, warehouse_id)
    - ref 非空，用于业务幂等
    - delta/after_qty 使用整型，配合 v2 “件数级”余额

    Phase 3.7-A 扩展：
    - trace_id：跨表 trace
    - production_date / expiry_date：用于仅靠 ledger 重建批次生命周期

    Phase 3.8（已落地）：
    - sub_reason：业务细分（PO_RECEIPT / COUNT_ADJUST / ORDER_SHIP ...）

    Phase 3.11（本次启动长期）：
    - reason_canon：reason 的稳定口径（RECEIPT / SHIPMENT / ADJUSTMENT）
      注意：不替换原 reason，避免破坏幂等与历史兼容。
    """

    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    warehouse_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    batch_code: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)

    reason: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    reason_canon: Mapped[str | None] = mapped_column(sa.String(32), nullable=True, index=True)

    sub_reason: Mapped[str | None] = mapped_column(sa.String(32), nullable=True, index=True)

    ref: Mapped[str] = mapped_column(sa.String(128), nullable=False)  # NOT NULL for idempotency
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
            "batch_code",
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
