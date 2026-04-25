# app/shipping_assist/billing/models/carrier_bill_item.py
# Domain move: carrier bill item ORM belongs to TMS billing.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CarrierBillItem(Base):
    """
    快递公司对账单原始明细表 carrier_bill_items

    语义定位：
    - 承载快递公司发来的账单行原始证据；
    - 当前阶段负责“幂等导入 + 查询”；
    - 不承担自动对账结果，不回写 shipping_records；
    - 不再保留 import_batch_no；
    - 业务唯一键为 carrier_code + tracking_no。
    """

    __tablename__ = "carrier_bill_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    carrier_code: Mapped[str] = mapped_column(String(32), nullable=False)
    bill_month: Mapped[str | None] = mapped_column(String(16), nullable=True)

    tracking_no: Mapped[str] = mapped_column(String(128), nullable=False)
    business_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    destination_province: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination_city: Mapped[str | None] = mapped_column(String(64), nullable=True)

    billing_weight_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )
    freight_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    surcharge_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    total_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    settlement_object: Mapped[str | None] = mapped_column(String(128), nullable=True)
    order_customer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    network_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_customer: Mapped[str | None] = mapped_column(String(128), nullable=True)

    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "carrier_code",
            "tracking_no",
            name="uq_carrier_bill_items_carrier_tracking",
        ),
        Index("ix_carrier_bill_items_tracking_no", "tracking_no"),
        Index("ix_carrier_bill_items_carrier_tracking", "carrier_code", "tracking_no"),
        Index("ix_carrier_bill_items_business_time", "business_time"),
    )

    def __repr__(self) -> str:
        return (
            f"<CarrierBillItem id={self.id} "
            f"carrier_code={self.carrier_code} "
            f"tracking_no={self.tracking_no}>"
        )
