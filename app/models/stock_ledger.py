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
    """

    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    warehouse_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    batch_code: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)

    reason: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    ref: Mapped[str] = mapped_column(sa.String(128), nullable=False)  # NOT NULL for idempotency
    ref_line: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)

    delta: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    after_qty: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    occurred_at: Mapped[sa.DateTime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Phase 3.7-A: 跨表 trace
    trace_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    # Phase 3.7-A: 批次日期信息（与 DB schema 对齐）
    production_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)

    __table_args__ = (
        # 与 DB 中迁移对齐的唯一约束（已存在于表结构中）
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
    )

    def __repr__(self) -> str:
        return (
            f"<Ledger {self.reason} wh={self.warehouse_id} item={self.item_id} "
            f"code={self.batch_code} delta={self.delta} after={self.after_qty} "
            f"prod={self.production_date} exp={self.expiry_date} "
            f"trace_id={self.trace_id}>"
        )
