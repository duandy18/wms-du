# app/shipping_assist/shipment/models/transport_shipment.py
# Domain move: transport shipment ORM belongs to TMS shipment.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TransportShipment(Base):
    """
    TMS / Shipment 主实体表 transport_shipments

    语义定位：
    - 该表是 Shipment 的主实体真相；
    - 执行证据以 quote_snapshot 固化；
    - shipping_records 仅作为 ledger / projection / reports source，
      不再承担 Shipment 主实体职责。

    当前状态合同（Phase-3 第三刀-A）：
    - 仅允许最小稳定状态集合：
      IN_TRANSIT / DELIVERED / LOST / RETURNED
    - 预留执行前态与模糊失败态不纳入当前主状态合同。
    """

    __tablename__ = "transport_shipments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 业务主身份
    order_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    store_code: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 执行锚点
    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    shipping_provider_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("shipping_providers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Quote -> Shipment 执行证据
    quote_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # 包裹信息
    weight_kg: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False)

    # 收件信息
    receiver_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    receiver_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    district: Mapped[str | None] = mapped_column(String(64), nullable=True)
    address_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 执行结果
    tracking_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shipping_provider_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shipping_provider_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    delivery_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "platform",
            "store_code",
            "order_ref",
            name="uq_transport_shipments_platform_store_ref",
        ),
        CheckConstraint("weight_kg > 0", name="ck_transport_shipments_weight_kg_positive"),
        CheckConstraint(
            "status IN ('IN_TRANSIT', 'DELIVERED', 'LOST', 'RETURNED')",
            name="ck_transport_shipments_status_valid",
        ),
        CheckConstraint(
            "jsonb_typeof(quote_snapshot) = 'object'",
            name="ck_transport_shipments_quote_snapshot_object",
        ),
        CheckConstraint(
            "(error_code IS NULL AND error_message IS NULL) OR (error_code IS NOT NULL)",
            name="ck_transport_shipments_error_pair",
        ),
        Index("ix_transport_shipments_trace_id", "trace_id"),
        Index("ix_transport_shipments_provider_id", "shipping_provider_id"),
        Index("ix_transport_shipments_warehouse_id", "warehouse_id"),
        Index("ix_transport_shipments_status", "status"),
        Index("ix_transport_shipments_delivery_time", "delivery_time"),
        Index("ix_transport_shipments_created_at", "created_at"),
        Index("ix_transport_shipments_ref_time", "order_ref", "created_at"),
        Index(
            "uq_transport_shipments_provider_tracking_notnull",
            "shipping_provider_id",
            "tracking_no",
            unique=True,
            postgresql_where=text("tracking_no IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TransportShipment id={self.id} ref={self.order_ref} "
            f"platform={self.platform} store_code={self.store_code} "
            f"provider_id={self.shipping_provider_id} "
            f"tracking_no={self.tracking_no} status={self.status}>"
        )
