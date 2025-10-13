# app/models/location.py
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint, Index
from sqlalchemy.orm import relationship

from app.db.base import Base


class Location(Base):
    """
    库位模型（与数据库结构对齐）：
    - 必须隶属于某个仓库：warehouse_id → warehouses.id
    - 不与 batches / stock_ledger 直接声明关系（当前无可用外键推断）
    """
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    warehouse_id = Column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        # 同一仓库下库位名唯一（按需保留）
        UniqueConstraint("warehouse_id", "name", name="uq_locations_wh_name"),
        Index("ix_locations_wh", "warehouse_id"),
    )

    # --- 只保留能通过真实外键推断出来的关系 ---
    warehouse = relationship("Warehouse", back_populates="locations")

    # 如果你的 stocks 表有 location_id → locations.id 外键，这个关系就成立；否则删掉。
    stocks = relationship(
        "Stock",
        back_populates="location",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # 重要：当前数据库没有从 stock_ledger 指向 locations 的外键，去掉以免触发 NoForeignKeysError
    # ledgers = relationship("StockLedger", back_populates="location")  # ❌ 删除
