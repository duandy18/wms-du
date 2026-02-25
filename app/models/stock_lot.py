# app/models/stock_lot.py
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.lot import Lot


class StockLot(Base):
    """
    Phase 4B：lot 维度库存余额投影（可 rebuild / 可对账）

    维度：(warehouse_id, item_id, lot_id|NULL)

    - qty 为余额（在线由 StockService.adjust 双写维护；也可通过 ledger rebuild）
    - lot_id 允许为 NULL：表示“无 lot 槽位”
    - (item_id, warehouse_id) 下只允许存在一个 NULL 槽位：
      通过生成列 lot_id_key = COALESCE(lot_id,0) 参与唯一性（见迁移）
    """

    __tablename__ = "stocks_lot"

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

    # ✅ 允许 NULL：NULL 表示“无 lot”
    lot_id: Mapped[int | None] = mapped_column(
        sa.Integer,
        sa.ForeignKey("lots.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # ✅ 生成列：把 NULL 映射为稳定 sentinel，参与唯一性
    lot_id_key: Mapped[int] = mapped_column(
        sa.Integer,
        sa.Computed("coalesce(lot_id, 0)", persisted=True),
        nullable=False,
        index=True,
    )

    qty: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    __table_args__ = (
        sa.UniqueConstraint("item_id", "warehouse_id", "lot_id_key", name="uq_stocks_lot_item_wh_lot"),
        Index("ix_stocks_lot_item_wh_lot", "item_id", "warehouse_id", "lot_id"),
    )

    warehouse = relationship("Warehouse", lazy="selectin")
    item = relationship("Item", lazy="selectin")
    lot = relationship(Lot, lazy="selectin")

    def __repr__(self) -> str:
        return f"<StockLot wh={self.warehouse_id} item={self.item_id} lot={self.lot_id} qty={self.qty}>"
