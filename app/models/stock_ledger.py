# app/models/stock_ledger.py
from __future__ import annotations

from datetime import datetime

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

    # 与数据库保持一致的类型/长度
    reason: Mapped[str] = mapped_column(String(64), nullable=False)

    # 建议数量使用 Numeric(18,6)，与你当前 DB 一致
    after_qty: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    delta: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ⚠️ 关键修复：ref 非空；ref_line 为 Integer（之前是 String 导致 PG 类型不匹配）
    ref: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    ref_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # 仅与 Stock 建关系（当前台账不含 batch_id 外键）
    stock: Mapped[Stock] = relationship("Stock", back_populates="ledgers", lazy="selectin")

    __table_args__ = (
        # 与迁移保持一致的唯一索引： (reason, ref, ref_line, stock_id)
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
