from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, DateTime, Numeric, String, Enum, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .item import Item
    from .order_item import OrderItem
    from .order_logistics import OrderLogistics


class Order(Base):
    """
    订单头（orders）

    注意：
    - 这里只映射已经在 SQL 中明确使用过的列（platform/shop_id/ext_order_no/status 等）；
    - 其它可能存在的列（如 extras / warehouse_id）仍通过原有 text SQL 访问，
      避免在不同迁移状态下出现 ORM → DB 不一致的问题。
    """

    __tablename__ = "orders"
    __allow_unmapped__ = True  # 保持对历史/未映射列的兼容

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # ✅ Scope（Phase 3 起点：订单域进入双宇宙）
    scope: Mapped[str] = mapped_column(
        Enum("PROD", "DRILL", name="biz_scope"),
        nullable=False,
        comment="订单 scope（PROD/DRILL）。DRILL 与 PROD 订单宇宙隔离。",
    )

    # 平台 + 店铺 + 外部订单号（业务主键三件套）
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

    # 订单状态（目前多为字符串，后续可收敛到枚举）
    status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="订单状态（CREATED / PAID / SHIPPED / CANCELED / RETURNED 等）",
    )

    # 买家信息（快照）
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

    # 金额信息（字符串形式由 OrderService.ingest 负责规范化）
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

    # trace_id：订单在全链路 trace 中的主键
    trace_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="链路 trace_id，用于 TraceService 聚合",
    )

    # 创建 & 更新时间
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

    # ------- 关系：行项目、商品、物流记录 ------- #

    # 强关系：一对多（写路径）
    order_items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    # 便捷只读：多对多（读路径，避免误写）
    items: Mapped[List["Item"]] = relationship(
        "Item",
        secondary="order_items",
        viewonly=True,
        lazy="selectin",
        back_populates="orders",
    )

    # 物流记录（常见为 0..n）
    logistics: Mapped[List["OrderLogistics"]] = relationship(
        "OrderLogistics",
        primaryjoin="Order.id == foreign(OrderLogistics.order_id)",
        back_populates="order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} "
            f"scope={getattr(self, 'scope', None)} "
            f"{self.platform}/{self.shop_id} ext={self.ext_order_no} "
            f"status={self.status} trace={self.trace_id}>"
        )
