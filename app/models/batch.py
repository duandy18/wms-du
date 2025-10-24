from __future__ import annotations
from sqlalchemy import CheckConstraint, Column, Date, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import synonym
from app.db.base import Base


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, nullable=False)

    batch_code = Column(String(64), nullable=False)  # 物理列
    code = synonym("batch_code")                     # 兼容旧引用

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
