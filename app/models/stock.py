# app/models/stock.py
from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Index,
    CheckConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Stock(Base):
    """
    汇总库存（与数据库结构对齐）：
    - 维度：item_id + location_id
    - 数量列：qty（非负）
    - 不与 stock_ledger 声明关系（当前表无可用外键）
    """
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True)

    item_id = Column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    location_id = Column(
        Integer,
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    qty = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("item_id", "location_id", name="uq_stocks_item_loc"),
        CheckConstraint("qty >= 0", name="ck_stocks_qty_nonneg"),
        Index("ix_stocks_item_loc", "item_id", "location_id"),
    )

    # 仅保留真实外键的关系
    item = relationship("Item", back_populates="stocks")
    location = relationship("Location", back_populates="stocks")

    # 重要：当前数据库没有从 stock_ledger 指向 stocks 的外键，下面这句不要加
    # ledgers = relationship("StockLedger", back_populates="stock")
