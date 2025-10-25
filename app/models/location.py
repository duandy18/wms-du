from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Index, Integer, String, UniqueConstraint
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
        UniqueConstraint("warehouse_id", "name", name="uq_locations_wh_name"),
        Index("ix_locations_wh", "warehouse_id"),
    )

    warehouse = relationship("Warehouse", back_populates="locations")
    stocks = relationship(
        "Stock",
        back_populates="location",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
