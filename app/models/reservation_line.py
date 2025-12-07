# app/models/reservation_line.py
from __future__ import annotations

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ReservationLine(Base):
    """库存预留明细 reservation_lines（Soft Reserve：只占位、不动实仓）"""

    __tablename__ = "reservation_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reservation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False
    )
    ref_line: Mapped[int] = mapped_column(Integer, nullable=False)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)

    # Soft Reserve 需要新增的消耗与状态
    consumed_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="open"
    )  # open|consumed|canceled
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("reservation_id", "ref_line", name="ix_reservation_lines_res_refline"),
        Index("ix_reservation_lines_item", "item_id"),
        Index("ix_reservation_lines_ref_line", "ref_line"),
        Index("ix_reserve_line_item_queue", "item_id", "status", "created_at"),
    )

    reservation = relationship("Reservation", back_populates="lines", lazy="selectin")

    def __repr__(self):
        return f"<ReservationLine id={self.id} item={self.item_id} qty={self.qty} consumed={self.consumed_qty}>"
