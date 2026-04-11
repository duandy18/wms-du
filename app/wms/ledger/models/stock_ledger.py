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

    Phase M-2 / Phase 3 终态（lot-only）：

    - lot_id 为唯一结构身份锚点（NOT NULL）
    - batch_code 已从 stock_ledger 移除（不再展示/不再参与任何结构语义）
    - lot 维度一致性由复合外键强制：
      (lot_id, warehouse_id, item_id) -> lots(id, warehouse_id, item_id)
    """

    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    warehouse_id: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        index=True,
    )

    item_id: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        index=True,
    )

    # ✅ 结构层唯一锚点（必须存在）
    # NOTE: Phase 3 uses composite FK in __table_args__ (do NOT keep single-column FK here)
    lot_id: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    reason_canon: Mapped[str | None] = mapped_column(
        sa.String(32),
        nullable=True,
        index=True,
    )

    sub_reason: Mapped[str | None] = mapped_column(
        sa.String(32),
        nullable=True,
        index=True,
    )

    ref: Mapped[str] = mapped_column(sa.String(128), nullable=False)

    ref_line: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=1,
    )

    delta: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    after_qty: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    occurred_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    trace_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )

    production_date: Mapped[date | None] = mapped_column(
        sa.Date,
        nullable=True,
    )

    expiry_date: Mapped[date | None] = mapped_column(
        sa.Date,
        nullable=True,
    )

    __table_args__ = (
        # Phase 3：锁死 lot 维度一致性（与 migration 对齐）
        sa.ForeignKeyConstraint(
            ["lot_id", "warehouse_id", "item_id"],
            ["lots.id", "lots.warehouse_id", "lots.item_id"],
            name="fk_stock_ledger_lot_dims",
            ondelete="RESTRICT",
        ),
        # ✅ 幂等唯一键仅基于 lot 结构
        sa.UniqueConstraint(
            "reason",
            "ref",
            "ref_line",
            "item_id",
            "warehouse_id",
            "lot_id",
            name="uq_ledger_wh_lot_item_reason_ref_line",
        ),
        # 结构查询主维度
        sa.Index(
            "ix_ledger_dims",
            "item_id",
            "warehouse_id",
            "lot_id",
        ),
        # ✅ occurred_at 单列索引：仅保留一个，与 DB 对齐（避免重复索引回潮）
        sa.Index("ix_stock_ledger_occurred_at", "occurred_at"),
        sa.Index("ix_stock_ledger_trace_id", "trace_id"),
        sa.Index("ix_stock_ledger_sub_reason_time", "sub_reason", "occurred_at"),
        sa.Index("ix_stock_ledger_reason_canon_time", "reason_canon", "occurred_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Ledger {self.reason}/{self.reason_canon}/{self.sub_reason} "
            f"wh={self.warehouse_id} item={self.item_id} "
            f"lot={self.lot_id} "
            f"delta={self.delta} after={self.after_qty} "
            f"prod={self.production_date} exp={self.expiry_date} "
            f"trace_id={self.trace_id}>"
        )
