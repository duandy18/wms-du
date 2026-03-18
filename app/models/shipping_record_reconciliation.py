# app/models/shipping_record_reconciliation.py
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ReconciliationStatus = Literal["diff", "bill_only", "record_only"]


class ShippingRecordReconciliation(Base):
    """
    发货对账异常表 shipping_record_reconciliations

    语义定位：
    - 本表只记录“异常态”，不记录 matched；
    - 异常态包括：
      * diff        = 账单与台帐均存在，但存在差异
      * bill_only   = 账单存在，但台帐不存在
      * record_only = 台帐存在，但账单不存在
    - 原始来源是 shipping_records（物流台帐）与 carrier_bill_items（快递账单）；
    - 当前系统已取消 batch 作为主链，不再依赖 import_batch_id；
    - import_batch_no 仅保留为展示/来源备注字段；
    - adjust_amount 为人工处理结果：
      * NULL = 尚未处理
      * 0 = 接受账单，不调整
      * 负数 = 向快递公司追回金额
    """

    __tablename__ = "shipping_record_reconciliations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    status: Mapped[ReconciliationStatus] = mapped_column(
        String(16),
        nullable=False,
    )

    carrier_code: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    import_batch_no: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="",
    )

    shipping_record_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("shipping_records.id", ondelete="RESTRICT"),
        nullable=True,
    )

    carrier_bill_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("carrier_bill_items.id", ondelete="RESTRICT"),
        nullable=True,
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('diff', 'bill_only', 'record_only')",
            name="ck_shipping_record_reconciliations_status",
        ),
        CheckConstraint(
            """
            (
              (status = 'diff' AND shipping_record_id IS NOT NULL AND carrier_bill_item_id IS NOT NULL)
              OR
              (status = 'bill_only' AND shipping_record_id IS NULL AND carrier_bill_item_id IS NOT NULL)
              OR
              (status = 'record_only' AND shipping_record_id IS NOT NULL AND carrier_bill_item_id IS NULL)
            )
            """,
            name="ck_shipping_record_reconciliations_status_shape",
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
            "ix_shipping_record_reconciliations_carrier_status",
            "carrier_code",
            "status",
        ),
        Index(
            "uq_shipping_record_reconciliations_shipping_record_id_notnull",
            "shipping_record_id",
            unique=True,
            postgresql_where=text("shipping_record_id IS NOT NULL"),
        ),
        Index(
            "uq_shipping_record_reconciliations_bill_item_id_notnull",
            "carrier_bill_item_id",
            unique=True,
            postgresql_where=text("carrier_bill_item_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingRecordReconciliation id={self.id} "
            f"status={self.status} "
            f"carrier_code={self.carrier_code} "
            f"import_batch_no={self.import_batch_no} "
            f"shipping_record_id={self.shipping_record_id} "
            f"bill_item_id={self.carrier_bill_item_id} "
            f"tracking_no={self.tracking_no}>"
        )
