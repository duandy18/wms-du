# app/models/stock_ledger.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StockLedger(Base):
    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    stock_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocks.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # 业务字段
    reason: Mapped[str] = mapped_column(String(64), nullable=False)            # INBOUND / OUTBOUND / ADJUST / TRANSFER ...
    ref: Mapped[str] = mapped_column(String(128), nullable=False, default="")  # 业务单据号
    ref_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 行号

    # 数量：高精度以避免累计误差
    after_qty: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    delta: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 关系
    stock = relationship("Stock", back_populates="ledgers", lazy="selectin")

    __table_args__ = (
        # 唯一性：同一 stock 上，同一业务单据的同一行只能记录一次
        Index(
            "uq_ledger_reason_ref_refline_stock",
            "reason",
            "ref",
            "ref_line",
            "stock_id",
            unique=True,
        ),
        Index("ix_stock_ledger_stock_id", "stock_id"),
        Index("ix_stock_ledger_occurred_at", "occurred_at"),
    )
