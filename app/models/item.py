# app/models/item.py
from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Item(Base):
    __tablename__ = "items"  # 复数表名

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # 当前可用库存数量（如不使用，可保留占位或后续迁移移除）
    qty_available: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 时间戳（可选；若你的项目未使用，可删去）
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # === 反向关系 ===
    # 到订单明细（若你的项目存在 OrderItem）
    lines = relationship(
        "OrderItem",
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # 到现势库存
    stocks = relationship(
        "Stock",
        back_populates="item",
        cascade="all, delete-orphan",
    )
    # ✅ 新增：到批次（与 Batch.item = relationship(..., back_populates="item") 对应）
    batches = relationship("Batch", back_populates="item")
