# app/models/batch.py
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    Index,
    Integer,
    String,
    UniqueConstraint,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.db.base import Base


class Batch(Base):
    """
    批次（强契约·现代声明式）
    - 物理列：id / item_id(FK) / batch_code / location_id(FK) / warehouse_id(FK) /
              production_date / expiry_date / qty
    - 唯一键：item_id + warehouse_id + location_id + batch_code
    - 与 Item 建立双向关系（Item.batches <-> Batch.item）
    """

    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 外键对齐数据库迁移
    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
        index=True,
    )

    # 关键：物理列名为 batch_code
    batch_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 兼容：旧代码使用 Batch.code
    code = synonym("batch_code")

    location_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("locations.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
        index=True,
    )

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT", onupdate="RESTRICT"),
        nullable=False,
        index=True,
    )

    production_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 关系（最关键的是与 Item 的反向关系，用于消除 NoForeignKeysError）
    item: Mapped["Item"] = relationship(
        "Item",
        back_populates="batches",
        lazy="selectin",
    )
    # 如需也建立到 Location/Warehouse 的关系，可按需开启：
    # location: Mapped["Location"] = relationship("Location", lazy="selectin")
    # warehouse: Mapped["Warehouse"] = relationship("Warehouse", lazy="selectin")

    __table_args__ = (
        # 与现库对齐：四列唯一键（幂等）
        UniqueConstraint(
            "item_id", "warehouse_id", "location_id", "batch_code",
            name="uq_batches_item_wh_loc_code",
        ),
        CheckConstraint("qty >= 0", name="ck_batch_qty_nonneg"),
        Index("ix_batches_code", "batch_code"),
        Index("ix_batches_expiry", "expiry_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<Batch id={self.id} item_id={self.item_id} wh={self.warehouse_id} "
            f"loc={self.location_id} code={self.batch_code!r} qty={self.qty}>"
        )
