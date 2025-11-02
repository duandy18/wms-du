# app/models/stock_ledger.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    # 仅用于类型提示，避免循环导入
    from app.models.stock import Stock
    from app.models.item import Item


class StockLedger(Base):
    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # === 主轴：stock_id（与幂等键配合） ===
    stock_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stocks.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # === 强契约：直接落库 item_id，便于聚合与查询 ===
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", onupdate="RESTRICT", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # === 业务语义字段 ===
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    after_qty: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    delta: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    # 具时区时间；存库建议使用 UTC（展示层再转 Asia/Shanghai）
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 引用信息
    ref: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    ref_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # 关系（轻量）
    stock: Mapped["Stock"] = relationship("Stock", lazy="selectin")
    item: Mapped["Item"] = relationship("Item", lazy="selectin")

    __table_args__ = (
        # 幂等唯一约束：(reason, ref, ref_line, stock_id)
        Index(
            "uq_ledger_reason_ref_refline_stock",
            "reason",
            "ref",
            "ref_line",
            "stock_id",
            unique=True,
        ),
        # 常见检索：时间线
        Index("ix_stock_ledger_occurred_at", "occurred_at"),
        # 常见检索：按商品+时间
        Index("ix_stock_ledger_item_time", "item_id", "occurred_at"),
        # 快速定位 stock 维度
        Index("ix_stock_ledger_stock_id", "stock_id"),
    )
