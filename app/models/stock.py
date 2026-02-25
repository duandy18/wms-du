# app/models/stock.py
from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.db.base import Base


class Stock(Base):
    """
    Legacy（Phase 4E 已退场）：

    v2 时代库存余额维度 (warehouse_id, item_id, batch_code|NULL)

    ⚠️ Phase 4E 真收口后：
    - 主余额源：stocks_lot
    - 批次主档：lots
    - stocks / batches 仅作为历史遗留（可能已 rename 为 *_legacy，最终会 DROP）

    本模型保留目的：
    - 避免历史 import 直接炸（便于失败栈优先法暴露调用点）
    - 但禁止再通过本模型隐式访问 batches（因此 expiry_date 不再查询 batches）
    """

    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    warehouse_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ✅ 允许 NULL：NULL 表示“无批次”
    batch_code: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    # ✅ 生成列：把 NULL 映射为稳定 sentinel，参与唯一性
    batch_code_key: Mapped[str] = mapped_column(
        sa.String(64),
        sa.Computed("coalesce(batch_code, '__NULL_BATCH__')", persisted=True),
        nullable=False,
        index=True,
    )

    qty: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    __table_args__ = (
        sa.UniqueConstraint("item_id", "warehouse_id", "batch_code_key", name="uq_stocks_item_wh_batch"),
        Index("ix_stocks_item_wh_batch", "item_id", "warehouse_id", "batch_code"),
    )

    warehouse = relationship("Warehouse", lazy="selectin")
    item = relationship("Item", lazy="selectin")

    # Phase 4E：禁止通过 stocks 模型再去 JOIN/SELECT batches
    # - 保留字段名以兼容旧代码的属性访问
    # - 但值恒为 NULL（真正的 expiry_date 现在来自 lots.expiry_date）
    expiry_date: Mapped[date | None] = column_property(sa.cast(sa.null(), sa.Date))

    def __repr__(self) -> str:
        return f"<Stock wh={self.warehouse_id} item={self.item_id} code={self.batch_code} qty={self.qty}>"
