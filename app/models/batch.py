# app/models/batch.py
from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Batch(Base):
    """
    批次模型：在“item + location + batch_code”维度上唯一。
    用途：追溯、退货、质检、保质期管理。
    """

    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 业务批次码（人为/系统生成皆可）
    batch_code = Column(String(64), nullable=False)

    # 关联维度：商品 / 库位 / 仓库
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False)

    # 生产/到期（可空）
    production_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)

    # 现势批次数量（非负）
    qty = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        # 一个库位下，同一商品的同一批次码唯一
        UniqueConstraint("item_id", "location_id", "batch_code", name="uq_batch_item_loc_code"),
        # 不允许批次数量为负
        CheckConstraint("qty >= 0", name="ck_batch_qty_nonneg"),
        # 常用查询索引
        Index("ix_batches_code", "batch_code"),
        Index("ix_batches_expiry", "expiry_date"),
    )

    # 关系
    item = relationship("Item", back_populates="batches")
    location = relationship("Location", back_populates="batches")
    warehouse = relationship("Warehouse", back_populates="batches")

    # 若你要在流水里记录 batch_id，可开启反向关系
    ledgers = relationship(
        "StockLedger", back_populates="batch", cascade="all, delete-orphan", passive_deletes=True
    )
