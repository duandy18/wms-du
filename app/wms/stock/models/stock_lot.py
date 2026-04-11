# app/models/stock_lot.py
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.wms.stock.models.lot import Lot


class StockLot(Base):
    """
    Phase M-5 终态：lot 维度库存余额（可 rebuild / 可对账）

    维度：(warehouse_id, item_id, lot_id)

    - qty 为余额（在线由 StockService.adjust_lot 维护；也可通过 ledger rebuild）
    - lot_id 为结构身份锚点（NOT NULL）
      * “非批次商品”不是 NULL 槽位，而是 INTERNAL lot（lot_code 可能为 NULL，但 lot_id 仍存在）
      * 不使用 lot_id_key=0 / sentinel

    维度一致性由复合外键强制：
      (lot_id, warehouse_id, item_id) -> lots(id, warehouse_id, item_id)
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

    # ✅ DB 事实：NOT NULL
    lot_id: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
    )

    qty: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["lot_id", "warehouse_id", "item_id"],
            ["lots.id", "lots.warehouse_id", "lots.item_id"],
            name="fk_stocks_lot_lot_dims",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "item_id",
            "warehouse_id",
            "lot_id",
            name="uq_stocks_lot_item_wh_lot",
        ),
    )

    warehouse = relationship("Warehouse", lazy="selectin")
    item = relationship("Item", lazy="selectin")
    lot = relationship(Lot, lazy="selectin", viewonly=True, overlaps="warehouse,item")

    def __repr__(self) -> str:
        return f"<StockLot wh={self.warehouse_id} item={self.item_id} lot={self.lot_id} qty={self.qty}>"
