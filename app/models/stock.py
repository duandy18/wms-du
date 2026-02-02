# app/models/stock.py
from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.db.base import Base


class Stock(Base):
    """
    v2：库存余额维度 (warehouse_id, item_id, batch_code|NULL)

    - qty 为唯一真实库存来源
    - expiry_date：从 batches 表按 (item_id, warehouse_id, batch_code) 精确映射
                 （当 batch_code 为 NULL 时，expiry_date 必然为 NULL）
    - location_id：兼容旧时代，始终固定为 1

    ✅ 本窗口演进：
    - batch_code 允许为 NULL，用于表达“无批次商品”的真实槽位
    - (item_id, warehouse_id) 下只允许存在一个 NULL 槽位：
      通过生成列 batch_code_key = COALESCE(batch_code,'__NULL_BATCH__') 参与唯一性（见迁移）

    ✅ Route 2.3：
    - 已彻底删除 stocks.qty_on_hand（事实列收敛到 stocks.qty）
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
        # ✅ 唯一性用 batch_code_key（DB 迁移会创建/重建同名约束）
        sa.UniqueConstraint("item_id", "warehouse_id", "batch_code_key", name="uq_stocks_item_wh_batch"),
        Index("ix_stocks_item_wh_batch", "item_id", "warehouse_id", "batch_code"),
    )

    warehouse = relationship("Warehouse", lazy="selectin")
    item = relationship("Item", lazy="selectin")

    # ★ Batch v3 兼容：按 仓 + 商品 + 批次 精确取 expiry_date
    # ✅ 主线 B：使用 IS NOT DISTINCT FROM，避免 NULL= NULL 吞数据（即使 batches 不会有 NULL 行，也让语义稳定）
    expiry_date: Mapped[date | None] = column_property(
        sa.select(sa.text("b.expiry_date"))
        .select_from(sa.text("batches AS b"))
        .where(sa.text("b.item_id = stocks.item_id"))
        .where(sa.text("b.warehouse_id = stocks.warehouse_id"))
        .where(sa.text("b.batch_code IS NOT DISTINCT FROM stocks.batch_code"))
        .limit(1)
        .scalar_subquery()
    )

    # 兼容旧用例：location_id 恒为 1
    location_id: Mapped[int] = column_property(sa.literal(1, type_=sa.Integer()))

    def __repr__(self) -> str:
        return (
            f"<Stock wh={self.warehouse_id} item={self.item_id} "
            f"code={self.batch_code} qty={self.qty}>"
        )
