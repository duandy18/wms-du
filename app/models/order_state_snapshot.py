from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderStateSnapshot(Base):
    """订单状态快照（平台/店铺/状态维度检索）"""

    __tablename__ = "order_state_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_order_state_snapshot_no", "order_no"),
        Index("ix_order_state_snapshot_state", "state"),
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return f"<OrderStateSnapshot order={self.order_no} state={self.state}>"
