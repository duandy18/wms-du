# app/shipping_assist/billing/models/shipping_bill_reconciliation_history.py
# Domain move: reconciliation history ORM belongs to TMS billing.
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ReconciliationHistoryResultStatus = Literal[
    "matched",
    "approved_bill_only",
    "resolved",
]
ApprovedReasonCode = Literal["matched", "approved_bill_only", "resolved"]


class ShippingBillReconciliationHistory(Base):
    """
    对账历史台账 shipping_bill_reconciliation_histories

    语义定位：
    - 一条账单明细（carrier_bill_item_id）只保留一条最终记录；
    - 唯一锚点是 carrier_bill_item_id；
    - matched：账单与我方记录直接对平；
    - approved_bill_only：只有账单、我方无记录，经人工确认后归档；
    - resolved：存在 diff，经人工 approve 后归档；
    - 本表只保留最终归档快照，不承担当前差异处理；
    - approved_reason_code 为最终确认结果 code；
    - approved_reason_text 为备注说明。
    """

    __tablename__ = "shipping_bill_reconciliation_histories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    carrier_bill_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("carrier_bill_items.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    shipping_record_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("shipping_records.id", ondelete="RESTRICT"),
        nullable=True,
    )

    shipping_provider_code: Mapped[str] = mapped_column(String(32), nullable=False)
    tracking_no: Mapped[str] = mapped_column(String(128), nullable=False)

    result_status: Mapped[ReconciliationHistoryResultStatus] = mapped_column(
        String(32),
        nullable=False,
    )

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

    approved_reason_code: Mapped[ApprovedReasonCode] = mapped_column(
        String(32),
        nullable=False,
    )

    approved_reason_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "result_status IN ('matched', 'approved_bill_only', 'resolved')",
            name="ck_shipping_bill_reconciliation_histories_result_status",
        ),
        CheckConstraint(
            "approved_reason_code IN ('matched', 'approved_bill_only', 'resolved')",
            name="ck_shipping_bill_reconciliation_histories_approved_reason_code",
        ),
        Index(
            "ix_shipping_bill_reconciliation_histories_tracking_no",
            "tracking_no",
        ),
        Index(
            "ix_shipping_bill_reconciliation_histories_provider_tracking",
            "shipping_provider_code",
            "tracking_no",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingBillReconciliationHistory id={self.id} "
            f"bill_item_id={self.carrier_bill_item_id} "
            f"result_status={self.result_status} "
            f"shipping_provider_code={self.shipping_provider_code} "
            f"tracking_no={self.tracking_no}>"
        )
