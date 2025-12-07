# app/models/stock.py
from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.db.base import Base


class Stock(Base):
    """
    v2：库存余额维度 (warehouse_id, item_id, batch_code)

    - qty 为唯一真实库存来源
    - expiry_date：从 batches 表按 (item_id, warehouse_id, batch_code) 精确映射
    - location_id：兼容旧时代，始终固定为 1
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
    batch_code: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    qty: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("item_id", "warehouse_id", "batch_code", name="uq_stocks_item_wh_batch"),
        Index("ix_stocks_item_wh_batch", "item_id", "warehouse_id", "batch_code"),
    )

    warehouse = relationship("Warehouse", lazy="selectin")
    item = relationship("Item", lazy="selectin")

    # ★ Batch v3 兼容：按 仓 + 商品 + 批次 精确取 expiry_date
    expiry_date: Mapped[date | None] = column_property(
        sa.select(sa.text("b.expiry_date"))
        .select_from(sa.text("batches AS b"))
        .where(sa.text("b.item_id = stocks.item_id"))
        .where(sa.text("b.warehouse_id = stocks.warehouse_id"))
        .where(sa.text("b.batch_code = stocks.batch_code"))
        .limit(1)
        .scalar_subquery()
    )

    # 兼容旧用例：location_id 恒为 1
    location_id: Mapped[int] = column_property(sa.literal(1, type_=sa.Integer()))

    @property
    def qty_on_hand(self) -> int:
        return int(self.qty or 0)

    def __repr__(self) -> str:
        return (
            f"<Stock wh={self.warehouse_id} item={self.item_id} "
            f"code={self.batch_code} qty={self.qty}>"
        )
