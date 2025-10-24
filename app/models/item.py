from __future__ import annotations

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Item(Base):
    __tablename__ = "items"  # 与实际表名一致（复数）

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # 新增：与数据库对齐（默认 'PCS'，不可为 NULL）
    unit: Mapped[str] = mapped_column(String(16), nullable=False, default="PCS")

    # 可用数量（如不使用，可后续迁移移除）
    qty_available: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 时间戳
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 关系：订单行（如存在）、库存
    lines = relationship(
        "OrderItem",
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    stocks = relationship(
        "Stock",
        back_populates="item",
        cascade="all, delete-orphan",
    )
    # batches = relationship("Batch", back_populates="item")  # 若后续补充 Batch 外键再启用
