# app/models/batch.py
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Batch(Base):
    """
    Batch v3 业务模型（以 batch_code 为唯一主键业务维度）

    批次主键维度：
        (item_id, warehouse_id, batch_code)

    批次属性：
        - production_date   生产日期（可空）
        - expiry_date       到期日期（FEFO 核心字段）
        - supplier_lot      原厂批号（可选）
        - created_at        首次出现时间（保留追溯能力）

    已移除旧字段：
        - qty                → 库存统一由 stocks 表承担
        - expire_at          → 旧字段，与 expiry_date 重叠
        - mfg_date           → 与 production_date 重叠
        - shelf_life_days    → Item 层才负责保质期
    """

    __tablename__ = "batches"

    # 主键（自动 ID）
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 所属商品 / 仓库
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
    )
    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 业务批次码（唯一 key）
    batch_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # 批次属性：生产日期 & 到期日期
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # 供应商批号（有则填，无则空）
    supplier_lot: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        # 批次业务层唯一约束：批次码在同商品同仓唯一
        UniqueConstraint(
            "item_id",
            "warehouse_id",
            "batch_code",
            name="uq_batches_item_wh_code",
        ),
        Index("ix_batches_item_wh_code", "item_id", "warehouse_id", "batch_code"),
        Index("ix_batches_item_id", "item_id"),
        Index("ix_batches_item_code", "item_id", "batch_code"),
        Index("ix_batches_batch_code", "batch_code"),
        Index("ix_batches_expiry_date", "expiry_date"),
        Index("ix_batches_production_date", "production_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<Batch id={self.id} "
            f"item={self.item_id} wh={self.warehouse_id} "
            f"code={self.batch_code} prod={self.production_date} "
            f"exp={self.expiry_date}>"
        )
