# app/models/stock_ledger.py
from __future__ import annotations

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Index,
    CheckConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class StockLedger(Base):
    """
    库存台账（严格对齐当前数据库结构）：
    仅包含：id / batch_id / delta / ref / created_at
    - 不声明 reason / after_qty / stock_id / item_id / location_id 等数据库里不存在的列
    """
    __tablename__ = "stock_ledger"

    id = Column(Integer, primary_key=True)

    batch_id = Column(
        Integer,
        ForeignKey("batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 变动数量：正=入，负=出（非零）
    delta = Column(Integer, nullable=False)

    # 业务参考号（可空），如 PO-1 / PW-1-in
    ref = Column(String(128), nullable=True)

    # 创建时间（DB 默认当前时间）
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint("delta <> 0", name="ck_ledger_delta_nonzero"),
        Index("ix_ledger_created", "created_at"),
    )

    # 关系：仅与 Batch 关联（可选）
    batch = relationship("Batch", back_populates="ledgers")
