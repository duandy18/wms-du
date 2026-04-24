# app/oms/orders/models/order_fulfillment.py
# Domain move: order fulfillment ORM belongs to OMS orders.
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderFulfillment(Base):
    """
    order_fulfillment：执行域 authority（Phase 5）

    - planned_warehouse_id：服务归属快照（planned）
    - actual_warehouse_id：执行仓事实（actual）
    - execution_stage：显式执行阶段真相（PICK / SHIP；NULL = 未进入执行链路）
    - ship_committed_at：进入出库裁决链路锚点（事实字段）
    - shipped_at：出库完成时间（事实字段）
    - fulfillment_status：路由态/阻断态/人工干预语义（禁止再存 SHIP_COMMITTED/SHIPPED）
    - blocked_reasons：阻断原因（jsonb）

    ⚠️ 索引以 migration 为准（不要在模型里 index=True 生成隐式索引）
    """

    __tablename__ = "order_fulfillment"

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("orders.id", ondelete="CASCADE"),
        primary_key=True,
    )

    planned_warehouse_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
    )

    actual_warehouse_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=True,
    )

    fulfillment_status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )

    blocked_reasons: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    execution_stage: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
    )

    ship_committed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    shipped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
