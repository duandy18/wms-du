# app/models/order.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enum import OrderStatus, OrderType  # 统一从集中枚举处导入

if TYPE_CHECKING:
    from app.models.order_item import OrderItem


class Order(Base):
    """
    订单主档（强契约 · 现代声明式）
    - 不改变现有表结构/枚举名：order_type, order_status
    - 时间列具时区；created_at/updated_at 默认写入 UTC（DB 侧 func.now()），updated_at 支持 onupdate
    """

    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_type_status", "order_type", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 业务主键
    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    # 枚举：与现库的 ENUM 名称完全一致（name 保持原有，避免迁移）
    order_type: Mapped[str] = mapped_column(SAEnum(OrderType, name="order_type"), index=True)
    status: Mapped[str] = mapped_column(SAEnum(OrderStatus, name="order_status"), index=True)

    # 可选维度（单据两端）
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 金额（保持精度/默认值）
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)

    # 具时区时间：DB 统一存 UTC（展示层再转 Asia/Shanghai）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 关系：订单 ↔ 明细
    lines: Mapped[List["OrderItem"]] = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Order id={self.id} no={self.order_no!r} type={self.order_type} status={self.status}>"
        )
