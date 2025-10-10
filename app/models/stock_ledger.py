# app/models/stock_ledger.py
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import relationship

from app.db.base import Base


class StockLedger(Base):
    """
    库存流水表：每次对 stocks 的调整，记录一条流水。
    - 粒度：面向 stock（item_id + location_id 的现势库存行）
    - 可选关联 batch：若本次调整发生在具体批次上
    - after_qty：调整后的 stocks.qty 快照，便于审计与对账
    """

    __tablename__ = "stock_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 指向粒度为 item + location 的现势库存记录
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)

    # 可选关联批次（若本次调整针对某个批次）
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="SET NULL"), nullable=True)

    # 本次调整的数量变化（允许负数；0 无意义，阻止）
    delta = Column(Integer, nullable=False)

    # 业务原因，如 INBOUND/OUTBOUND/ADJUST/RETURN/INVENTORY_COUNT 等
    reason = Column(String(64), nullable=False)

    # 外部参考号，如单据号、快递单号、上游系统 ID
    ref = Column(String(128), nullable=True)

    # 创建时间（UTC）
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 调整后现势库存快照（用于审计与对账）
    after_qty = Column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("delta <> 0", name="ck_ledger_delta_nonzero"),
        Index("ix_ledger_stock_time", "stock_id", "created_at"),
        Index("ix_ledger_batch_time", "batch_id", "created_at"),
    )

    # 关系
    stock = relationship("Stock", back_populates="ledgers", passive_deletes=True)
    batch = relationship("Batch", back_populates="ledgers")

    def __repr__(self) -> str:  # 调试友好
        return f"<StockLedger id={self.id} stock_id={self.stock_id} delta={self.delta} after={self.after_qty}>"
