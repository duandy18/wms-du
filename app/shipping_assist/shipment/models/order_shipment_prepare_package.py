# app/shipping_assist/shipment/models/order_shipment_prepare_package.py
# Domain move: order shipment prepare package ORM belongs to TMS shipment.
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderShipmentPreparePackage(Base):
    """
    order_shipment_prepare_packages：发运准备阶段包裹决策表

    职责：
      - 保存订单当前包裹方案
      - 保存包级发运决策事实：
        1) 第几个包
        2) 该包重量
        3) 该包从哪个仓发
        4) 该包算价状态
        5) 该包选择哪家承运商
        6) 该包锁定什么报价快照

    设计要点：
      - 一张订单可有多个包裹
      - package_no 从 1 开始，且在同一订单内唯一
      - 当前不引入长宽高，避免过度设计
      - 多仓拼单终态下，仓/价/承运商真相都在包级
    """

    __tablename__ = "order_shipment_prepare_packages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "orders.id",
            name="fk_order_shipment_prepare_packages_order",
            ondelete="CASCADE",
        ),
        nullable=False,
        comment="订单 ID",
    )

    package_no: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="包裹序号，从 1 开始",
    )

    weight_kg: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 3),
        nullable=True,
        comment="包裹重量（kg）",
    )

    warehouse_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
        comment="该包裹选定发货仓 warehouses.id",
    )

    pricing_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default="pending",
        comment="该包裹运价状态：pending / calculated",
    )

    selected_provider_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("shipping_providers.id", ondelete="SET NULL"),
        nullable=True,
        comment="该包裹已选承运商 shipping_providers.id",
    )

    selected_quote_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="该包裹已锁定报价快照",
    )

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

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "package_no",
            name="uq_order_shipment_prepare_packages_order_package_no",
        ),
        Index("ix_order_shipment_prepare_packages_order_id", "order_id"),
        Index(
            "ix_order_shipment_prepare_packages_order_package_no",
            "order_id",
            "package_no",
        ),
        Index("ix_order_shipment_prepare_packages_warehouse_id", "warehouse_id"),
        Index("ix_order_shipment_prepare_packages_pricing_status", "pricing_status"),
        Index(
            "ix_order_shipment_prepare_packages_selected_provider_id",
            "selected_provider_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            "<OrderShipmentPreparePackage "
            f"id={self.id} "
            f"order_id={self.order_id} "
            f"package_no={self.package_no} "
            f"weight_kg={self.weight_kg} "
            f"warehouse_id={self.warehouse_id} "
            f"pricing_status={self.pricing_status} "
            f"selected_provider_id={self.selected_provider_id}>"
        )
