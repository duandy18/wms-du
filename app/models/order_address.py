from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderAddress(Base):
    """
    订单地址信息表 order_address

    设计要点：
      - 一张订单最多一条地址（uq_order_address_order_id）
      - 与 orders 通过 order_id 外键关联，删除订单自动删除地址
      - 仅存储收货相关信息，物流承运信息仍在 OrderLogistics 中
    """

    __tablename__ = "order_address"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "orders.id",
            name="fk_order_address_order",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
    )

    receiver_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    receiver_phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    province: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    zipcode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("order_id", name="uq_order_address_order_id"),
        Index("ix_order_address_order_id", "order_id"),
        # 防止 Alembic autogen 再次对这个表做 diff
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return f"<OrderAddress id={self.id} order_id={self.order_id}>"
