# app/models/stock_ledger.py  —— 覆盖版
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
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
    reason:   Mapped[str]     = mapped_column(String(64),  nullable=False)            # INBOUND/OUTBOUND/ADJUST/TRANSFER...
    ref:      Mapped[str]     = mapped_column(String(128), nullable=False, default="")
    ref_line: Mapped[int]     = mapped_column(Integer,     nullable=False, default=1)

    item_id:    Mapped[int]       = mapped_column(Integer, nullable=False)
    after_qty:  Mapped[Decimal]   = mapped_column(Numeric(18, 6), nullable=False)
    delta:      Mapped[Decimal]   = mapped_column(Numeric(18, 6), nullable=False)
    occurred_at:Mapped[datetime]  = mapped_column(DateTime(timezone=True), nullable=False)

    stock = relationship("Stock", back_populates="ledgers", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("reason", "ref", "ref_line", "stock_id", name="uq_ledger_reason_ref_refline_stock"),
        Index("ix_stock_ledger_stock_id", "stock_id"),
        Index("ix_stock_ledger_occurred_at", "occurred_at"),
    )
