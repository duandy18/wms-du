# app/procurement/models/purchase_order_line_completion.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PurchaseOrderLineCompletion(Base):
    """
    采购行完成情况读模型表。

    设计定位：
    - 一行 = 一条采购单行当前完成情况
    - 不是采购计划真相表，也不是收货事实真相表
    - 服务采购页下半张卡“每行显示采购单的一行”
    """

    __tablename__ = "purchase_order_line_completion"

    __table_args__ = (
        CheckConstraint("qty_ordered_input > 0", name="ck_polc_qty_ordered_input_positive"),
        CheckConstraint("qty_ordered_base > 0", name="ck_polc_qty_ordered_base_positive"),
        CheckConstraint("qty_received_base >= 0", name="ck_polc_qty_received_base_nonneg"),
        CheckConstraint("qty_remaining_base >= 0", name="ck_polc_qty_remaining_base_nonneg"),
        CheckConstraint("purchase_ratio_to_base_snapshot >= 1", name="ck_polc_ratio_positive"),
        CheckConstraint(
            "qty_remaining_base = GREATEST(qty_ordered_base - qty_received_base, 0)",
            name="ck_polc_qty_remaining_consistent",
        ),
        CheckConstraint(
            "line_completion_status IN ('NOT_RECEIVED', 'PARTIAL', 'RECEIVED')",
            name="ck_polc_status",
        ),
        UniqueConstraint("po_id", "line_no", name="uq_polc_po_line_no"),
        sa.Index("ix_polc_po_id", "po_id"),
        sa.Index("ix_polc_po_no", "po_no"),
        sa.Index("ix_polc_supplier_id", "supplier_id"),
        sa.Index("ix_polc_warehouse_id", "warehouse_id"),
        sa.Index("ix_polc_item_id", "item_id"),
        sa.Index("ix_polc_item_sku", "item_sku"),
        sa.Index("ix_polc_completion_status", "line_completion_status"),
        sa.Index("ix_polc_purchase_time", "purchase_time"),
        sa.Index("ix_polc_last_received_at", "last_received_at"),
    )

    po_line_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("purchase_order_lines.id", ondelete="CASCADE"),
        primary_key=True,
    )

    po_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    po_no: Mapped[str] = mapped_column(String(64), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)

    warehouse_id: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_id: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    purchaser: Mapped[str] = mapped_column(String(64), nullable=False)
    purchase_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    item_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    spec_text: Mapped[str | None] = mapped_column(String(255), nullable=True)

    purchase_uom_id_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    purchase_uom_name_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    purchase_ratio_to_base_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)

    qty_ordered_input: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_ordered_base: Mapped[int] = mapped_column(Integer, nullable=False)

    supply_price_snapshot: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(12, 2),
        nullable=True,
    )
    planned_line_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(14, 2),
        nullable=False,
        server_default=text("0"),
    )

    qty_received_base: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    qty_remaining_base: Mapped[int] = mapped_column(Integer, nullable=False)
    line_completion_status: Mapped[str] = mapped_column(String(32), nullable=False)
    last_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

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
