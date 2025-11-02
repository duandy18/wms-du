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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StockSnapshot(Base):
    """
    日粒度库存快照（强契约版）
    - 维度：
        snapshot_date（对齐当天）、warehouse_id、location_id、item_id、batch_id(可空)
    - 指标：
        qty_on_hand、qty_allocated、qty_available（测试/路由会读取 qty_on_hand/qty_available）
    - 元数据：
        created_at（具时区，建议写入 UTC；展示层再转 Asia/Shanghai）
    """

    __tablename__ = "stock_snapshots"

    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 维度
    snapshot_date: Mapped[Date] = mapped_column(Date, index=True, nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )

    # 指标（整型，默认 0）
    qty_on_hand: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    qty_allocated: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    qty_available: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    # 可选质量/库龄信息
    expiry_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 元数据（UTC）
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # 轻量关系（按需 selectin）
    warehouse = relationship("Warehouse", lazy="selectin")
    location = relationship("Location", lazy="selectin")
    item = relationship("Item", lazy="selectin")
    batch = relationship("Batch", lazy="selectin")

    __table_args__ = (
        # 幂等唯一键：一日一粒度（同一仓/库位/商品/批次只有一条）
        UniqueConstraint(
            "snapshot_date",
            "warehouse_id",
            "location_id",
            "item_id",
            "batch_id",
            name="uq_stock_snapshot_grain",
        ),
        # 常用查询索引：趋势（按 item + date）
        Index("ix_ss_item_date", "item_id", "snapshot_date"),
        # 常用查询索引：仓内概览（按 warehouse + date）
        Index("ix_ss_wh_date", "warehouse_id", "snapshot_date"),
    )
