# app/models/reservation.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Reservation(Base):
    """Soft Reserve 头：只记录承诺，不动实仓"""

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 历史遗留列（保留兼容；Soft 语义不直接使用）
    item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    ref: Mapped[str] = mapped_column(Text, nullable=False)

    # created_at：与 DB 对齐，使用 timestamptz（timezone=True）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    order_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    batch_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # Soft Reserve 新增列（均已迁移到库）
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(128), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(Integer, nullable=False)

    locked_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 审计与 TTL
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    expire_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # 新增 trace_id：跨表 trace key（可空，方便渐进接入）
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_reservations_trace_id", "trace_id"),)

    # 关系
    lines = relationship("ReservationLine", back_populates="reservation", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Reservation id={self.id} ref={self.ref} "
            f"status={self.status} trace_id={self.trace_id}>"
        )
