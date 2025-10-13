# app/models/batch.py
from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship, synonym

from app.db.base import Base


class Batch(Base):
    """
    批次模型（与数据库结构对齐）：
    仅包含 id / item_id / code / production_date / expiry_date。
    - 物理列名统一为 'code'，并提供 Python 同义名 batch_code 兼容旧代码。
    - 同一 item 下的 code 唯一。
    """
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True)  # IDENTITY/serial，由数据库发号
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False, index=True)

    # 关键：数据库里就叫 'code'
    code = Column("code", String(64), nullable=False)
    # 兼容旧字段名 batch_code（应用层可继续使用）
    batch_code = synonym("code")

    production_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint("item_id", "code", name="uq_batches_item_code"),
        Index("ix_batches_item_code", "item_id", "code"),
        Index("ix_batches_expiry", "expiry_date"),
    )

    # 关系（按需保留；避免循环导入）
    item = relationship("Item", back_populates="batches", lazy="joined", viewonly=False)

    # 如果你的 StockLedger 里有 batch_id 外键，可以保留这个反向关系
    ledgers = relationship(
        "StockLedger",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
