# app/models/reservation_allocation.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReservationAllocations(Base):
    """
    LEGACY MODEL —— 旧版锁定来源台账（Lock-based Reservation）

    说明：
    - 该表最初用于“硬占用”流程（legacy lock-based reservation flow）：
        * legacy lock-based reservation flow: 扣减 stocks，写负向 RESERVE 台账，同时写入本表记录来源明细
        * reservation_release: 依据本表逐项恢复 stocks，写正向 RELEASE / RESERVE_EXPIRED 台账
    - 在当前 Soft Reserve v2 结构下：
        * 真实库存扣减统一通过 StockService.adjust + stock_ledger 完成
        * 新链路不再写入或读取 reservation_allocations
    - 保留此模型仅为历史数据和兼容考虑，新功能请勿再依赖本表。
    """

    __tablename__ = "reservation_allocations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    reservation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(Integer, nullable=False)
    location_id: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # 与历史 DB 结构对齐的 partial unique 索引：
    #   - uq_resalloc_null_batch  : (res,item,wh,loc) WHERE batch_id IS NULL
    #   - uq_resalloc_with_batch  : (res,item,wh,loc,batch_id) WHERE batch_id IS NOT NULL
    __table_args__ = (
        Index(
            "uq_resalloc_null_batch",
            "reservation_id",
            "item_id",
            "warehouse_id",
            "location_id",
            unique=True,
            postgresql_where=text("batch_id IS NULL"),
        ),
        Index(
            "uq_resalloc_with_batch",
            "reservation_id",
            "item_id",
            "warehouse_id",
            "location_id",
            "batch_id",
            unique=True,
            postgresql_where=text("batch_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ReservationAllocations id={self.id} rid={self.reservation_id} "
            f"item={self.item_id} wh={self.warehouse_id} loc={self.location_id} "
            f"batch={self.batch_id} qty={self.qty}>"
        )
