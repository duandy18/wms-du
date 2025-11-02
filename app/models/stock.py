# app/models/stock.py
from __future__ import annotations

from typing import List

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Stock(Base):
    """
    汇总库存（强契约·与数据库结构对齐）
    维度：item_id + location_id
    数量：qty（非负）
    关系：StockLedger.stock_id → stocks.id
    """
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    location_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # 库存数量（非负）
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("item_id", "location_id", name="uq_stocks_item_loc"),
        CheckConstraint("qty >= 0", name="ck_stocks_qty_nonneg"),
        Index("ix_stocks_item_loc", "item_id", "location_id"),
    )

    # ==== 关系 ====
    item: Mapped["Item"] = relationship(
        "Item",
        back_populates="stocks",
        lazy="selectin",
    )

    location: Mapped["Location"] = relationship(
        "Location",
        back_populates="stocks",
        lazy="selectin",
    )

    ledgers: Mapped[List["StockLedger"]] = relationship(
        "StockLedger",
        back_populates="stock",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Stock id={self.id} item_id={self.item_id} location_id={self.location_id} qty={self.qty}>"
