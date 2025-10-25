from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base


class Stock(Base):
    """
    汇总库存（与数据库结构对齐）：
    - 维度：item_id + location_id
    - 数量列：qty（非负）
    - 与 stock_ledger 通过 FK 关联（stock_ledger.stock_id → stocks.id）
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

    item = relationship("Item", back_populates="stocks")
    location = relationship("Location", back_populates="stocks")

    ledgers = relationship(
        "StockLedger",
        back_populates="stock",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
