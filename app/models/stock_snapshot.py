# app/models/stock_snapshot.py
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockSnapshot(Base):
    """
    日粒度库存快照（按你现有的字段设计）：
    - snapshot_date：对齐到当天（建议统一由任务对齐）
    - 维度：warehouse/location/item/batch
    - 指标：on_hand / allocated / available
    - ageing：可选的到期与库龄天数
    """

    __tablename__ = "stock_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 粒度与维度
    snapshot_date: Mapped[Date] = mapped_column(Date, index=True, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id"), index=True, nullable=False
    )
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True, nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True, nullable=False)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id"), index=True, nullable=True
    )

    # 指标（整型即可，与你当前模型保持一致）
    qty_on_hand: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default=text("0")
    )
    qty_allocated: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default=text("0")
    )
    qty_available: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default=text("0")
    )

    # 质量/库龄信息（可空）
    expiry_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 元数据
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # 幂等唯一键（与你已存在的命名保持一致）
        UniqueConstraint(
            "snapshot_date",
            "warehouse_id",
            "location_id",
            "item_id",
            "batch_id",
            name="uq_stock_snapshot_grain",
        ),
        # 常用查询索引：趋势查询（item + date），并发查询（warehouse + date）
        Index("ix_ss_item_date", "item_id", "snapshot_date"),
        Index("ix_ss_wh_date", "warehouse_id", "snapshot_date"),
    )
