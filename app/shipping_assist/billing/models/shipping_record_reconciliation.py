# app/shipping_assist/billing/models/shipping_record_reconciliation.py
# Domain move: shipping record reconciliation ORM belongs to TMS billing.
from __future__ import annotations

from datetime import datetime
from typing import Literal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ReconciliationStatus = Literal["diff", "bill_only"]
ApprovedReasonCode = Literal["matched", "approved_bill_only", "resolved"]


class ShippingRecordReconciliation(Base):
    """
    发货对账差异表 shipping_record_reconciliations

    语义定位：
    - 本表只记录“当前待处理差异”；
    - 当前正式对账主链只保留：
      * diff      = 账单与台账均存在，但存在差异
      * bill_only = 账单存在、我方缺记录，需人工确认后才能归档
    - 本表是当前待处理区，不是历史归档表；
    - 唯一锚点是快递网点账单 carrier_bill_items；
    - approved_reason_code 为最终确认结果 code；
    - approved_reason_text 为备注说明。
    """

    __tablename__ = "shipping_record_reconciliations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    status: Mapped[ReconciliationStatus] = mapped_column(
        String(16),
        nullable=False,
    )

    shipping_provider_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    shipping_record_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("shipping_records.id", ondelete="RESTRICT"),
        nullable=True,
    )

    carrier_bill_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("carrier_bill_items.id", ondelete="RESTRICT"),
        nullable=False,
    )

    tracking_no: Mapped[str] = mapped_column(String(128), nullable=False)

    weight_diff_kg: Mapped[float | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )

    cost_diff: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    adjust_amount: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    approved_reason_code: Mapped[ApprovedReasonCode | None] = mapped_column(
        String(32),
        nullable=True,
    )

    approved_reason_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('diff', 'bill_only')",
            name="ck_shipping_record_reconciliations_status",
        ),
        CheckConstraint(
            """
            (
              (status = 'diff' AND shipping_record_id IS NOT NULL AND carrier_bill_item_id IS NOT NULL)
              OR
              (status = 'bill_only' AND shipping_record_id IS NULL AND carrier_bill_item_id IS NOT NULL)
            )
            """,
            name="ck_shipping_record_reconciliations_status_shape",
        ),
        CheckConstraint(
            """
            (
              approved_reason_code IS NULL
              OR approved_reason_code IN ('matched', 'approved_bill_only', 'resolved')
            )
            """,
            name="ck_shipping_record_reconciliations_approved_reason_code",
        ),
        CheckConstraint(
            """
            (
              approved_at IS NULL
              OR approved_reason_code IS NOT NULL
            )
            """,
            name="ck_shipping_record_reconciliations_approved_requires_code",
        ),
        Index(
            "ix_shipping_record_reconciliations_tracking_no",
            "tracking_no",
        ),
        Index(
            "ix_shipping_record_reconciliations_bill_item_id",
            "carrier_bill_item_id",
        ),
        Index(
            "ix_shipping_record_reconciliations_provider_status",
            "shipping_provider_code",
            "status",
        ),
        Index(
            "uq_shipping_record_reconciliations_shipping_record_id_notnull",
            "shipping_record_id",
            unique=True,
            postgresql_where=text("shipping_record_id IS NOT NULL"),
        ),
        UniqueConstraint(
            "carrier_bill_item_id",
            name="uq_shipping_record_reconciliations_bill_item_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingRecordReconciliation id={self.id} "
            f"status={self.status} "
            f"shipping_provider_code={self.shipping_provider_code} "
            f"shipping_record_id={self.shipping_record_id} "
            f"bill_item_id={self.carrier_bill_item_id} "
            f"tracking_no={self.tracking_no}>"
        )
