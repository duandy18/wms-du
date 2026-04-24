# app/oms/orders/models/order.py
# Domain move: order ORM belongs to OMS orders.
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.pms.items.models.item import Item
    from app.oms.orders.models.order_item import OrderItem
    from app.oms.orders.models.order_logistics import OrderLogistics
    from app.models.store import Store


class Order(Base):
    """
    订单头（orders）

    当前阶段定位：
    - store_id：内部统一主身份（stores.id）
    - shop_id：兼容业务身份（暂保留，用于旧链路 / 展示 / 对账）
    - platform + ext_order_no：平台订单来源识别的一部分
    """

    __tablename__ = "orders"
    __allow_unmapped__ = True  # 保持对历史/未映射列的兼容

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    store_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
        comment="内部店铺主键（stores.id）",
    )

    platform: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="平台标识（如 PDD / TAOBAO / JD）",
    )

    shop_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="店铺 ID（字符串，与 stores.shop_id 对齐）",
    )

    ext_order_no: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="外部订单号 / 平台订单号",
    )

    status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="订单状态（CREATED / PAID / SHIPPED / CANCELED / RETURNED 等）",
    )

    buyer_name: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="买家姓名快照",
    )

    buyer_phone: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="买家电话快照",
    )

    order_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        comment="订单原始金额（含运费等，orders.order_amount）",
    )

    pay_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        comment="订单实付金额（orders.pay_amount）",
    )

    trace_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="链路 trace_id，用于 TraceService 聚合",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="订单创建时间",
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="订单最近更新时间",
    )

    store: Mapped["Store"] = relationship(
        "Store",
        lazy="selectin",
    )

    order_items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    items: Mapped[List["Item"]] = relationship(
        "Item",
        secondary="order_items",
        viewonly=True,
        lazy="selectin",
        back_populates="orders",
    )

    logistics: Mapped[List["OrderLogistics"]] = relationship(
        "OrderLogistics",
        primaryjoin="Order.id == foreign(OrderLogistics.order_id)",
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} store_id={self.store_id} "
            f"{self.platform}/{self.shop_id} ext={self.ext_order_no} "
            f"status={self.status} trace={self.trace_id}>"
        )
