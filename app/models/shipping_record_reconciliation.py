# app/models/shipping_record_reconciliation.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShippingRecordReconciliation(Base):
    """
    发货对账差异处理表 shipping_record_reconciliations

    语义定位：
    - 只记录“已匹配成功且存在差异”的运单；
    - 原始来源是 shipping_records（物流台帐）与 carrier_bill_items（快递账单）；
    - 不保存全量账单/台帐原始值，只保存差异结果与处理金额；
    - adjust_amount 为人工处理结果：
      * NULL = 尚未处理
      * 0 = 接受账单，不调整
      * 负数 = 向快递公司追回金额
    """

    __tablename__ = "shipping_record_reconciliations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    shipping_record_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("shipping_records.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_shipping_record_reconciliations_tracking_no", "tracking_no"),
        Index(
            "ix_shipping_record_reconciliations_bill_item_id",
            "carrier_bill_item_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ShippingRecordReconciliation id={self.id} "
            f"shipping_record_id={self.shipping_record_id} "
            f"bill_item_id={self.carrier_bill_item_id} "
            f"tracking_no={self.tracking_no}>"
        )
