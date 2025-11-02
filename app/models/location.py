# app/models/location.py
from __future__ import annotations

from typing import List

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Location(Base):
    """
    库位（强契约·现代声明式）
    - 必须隶属于某个仓库：warehouse_id → warehouses.id
    - 与 stocks 存在外键关系时，声明 back_populates 关系
    - 不声明到 StockLedger 的关系（当前无可用外键可推断）
    """

    __tablename__ = "locations"
    __table_args__ = (
        # 同一仓库下库位名唯一
        UniqueConstraint("warehouse_id", "name", name="uq_locations_wh_name"),
        Index("ix_locations_wh", "warehouse_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # === 关系（仅基于真实外键） ===
    warehouse: Mapped["Warehouse"] = relationship(
        "Warehouse",
        back_populates="locations",
        lazy="selectin",
    )

    # stocks.location_id → locations.id 外键存在时，这个关系成立
    stocks: Mapped[List["Stock"]] = relationship(
        "Stock",
        back_populates="location",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    # 不声明：当前数据库没有从 stock_ledger 指向 locations 的外键
    # ledgers: Mapped[List["StockLedger"]] = relationship("StockLedger", back_populates="location")

    def __repr__(self) -> str:
        return f"<Location id={self.id} wh={self.warehouse_id} name={self.name!r}>"
