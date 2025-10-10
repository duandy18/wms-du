# app/models/stock.py
from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False)

    # 关键：DB 列名是 qty，但在 Python 里用属性名 quantity
    quantity = Column("qty", Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("item_id", "location_id", name="uq_stocks_item_location"),)

    # 关系
    item = relationship("Item", back_populates="stocks")
    location = relationship("Location", back_populates="stocks")

    # 与库存流水的反向关系（v2 新增）
    ledgers = relationship(
        "StockLedger",
        back_populates="stock",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
