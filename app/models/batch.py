# app/models/batch.py
from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, Date, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import synonym

from app.db.base import Base


class Batch(Base):
    """
    与办公室库的 batches 表结构对齐：
    - 物理列：id / item_id / batch_code / location_id / warehouse_id / production_date / expiry_date / qty
    - 不声明到 Warehouse/Location/Item/StockLedger 的关系（当前库无相应外键；声明会触发 NoForeignKeysError）
    - 提供 code = synonym('batch_code') 兼容旧代码
    """

    __tablename__ = "batches"

    id = Column(Integer, primary_key=True)

    item_id = Column(Integer, nullable=False)

    # 关键：物理列名是 batch_code
    batch_code = Column(String(64), nullable=False)
    # 兼容：旧代码里用过 Batch.code
    code = synonym("batch_code")

    location_id = Column(Integer, nullable=False)
    warehouse_id = Column(Integer, nullable=False)

    production_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)

    qty = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("item_id", "location_id", "batch_code", name="uq_batch_item_loc_code"),
        CheckConstraint("qty >= 0", name="ck_batch_qty_nonneg"),
        Index("ix_batches_code", "batch_code"),
        Index("ix_batches_expiry", "expiry_date"),
    )
