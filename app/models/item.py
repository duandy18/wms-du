# app/models/item.py
from __future__ import annotations

from typing import List, Optional
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Item(Base):
    """
    商品主档（强契约·不改表结构）
    字段保持与现有表一致：
      - id            主键自增
      - sku           唯一、非空、可检索
      - name          非空
      - qty_available 整型、默认 0（若业务未用，可后续迁移清理）
      - created_at / updated_at 具时区，DB 层默认写入 UTC（展示层再转 Asia/Shanghai）
    关系：
      - lines    一对多 -> OrderItem（行项目）
      - stocks   一对多 -> Stock（现势库存）
      - batches  一对多 -> Batch（批次）【若你的 Batch 已声明 back_populates=item】
      - ledgers  一对多 -> StockLedger（台账）
    """

    __tablename__ = "items"  # 复数表名

    # === 基础字段（与原表一致） ===
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    qty_available: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # === 关系（仅声明、不中断现有表结构；使用 selectin 提升批量加载性能） ===
    lines: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    stocks: Mapped[List["Stock"]] = relationship(
        "Stock",
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    # 若你的 Batch 模型已定义：item = relationship("Item", back_populates="batches")
    # 这边即可打开对应 back_populates；若暂未定义，可先保持注释，不影响当前功能。
    batches: Mapped[List["Batch"]] = relationship(
        "Batch",
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    # 与台账的反向关系（StockLedger.item_id → items.id）
    ledgers: Mapped[List["StockLedger"]] = relationship(
        "StockLedger",
        back_populates="item",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Item id={self.id} sku={self.sku!r} name={self.name!r} qty_avail={self.qty_available}>"
