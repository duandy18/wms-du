# app/models/stock_ledger.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Numeric,
    ForeignKey,
    UniqueConstraint,
    Index,
)
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

    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    after_qty: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    delta: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ref_line: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # 只保留与 Stock 的关系；不要与 Batch 建立关系（当前台账不含 batch_id）
    stock: Mapped["Stock"] = relationship("Stock", back_populates="ledgers", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("reason", "ref", "ref_line", name="uq_stock_ledger_reason_ref_refline"),
        Index("ix_stock_ledger_stock_id", "stock_id"),
        Index("ix_stock_ledger_occurred_at", "occurred_at"),
    )
