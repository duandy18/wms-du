# app/models/inbound_receipt.py
from __future__ import annotations

from datetime import datetime, date as date_type
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InboundReceipt(Base):
    __tablename__ = "inbound_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", name="fk_inbound_receipts_warehouse", ondelete="RESTRICT"),
        nullable=False,
    )

    supplier_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", name="fk_inbound_receipts_supplier", ondelete="SET NULL"),
        nullable=True,
    )

    supplier_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    ref: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    lines: Mapped[List["InboundReceiptLine"]] = relationship(
        "InboundReceiptLine",
        back_populates="receipt",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class InboundReceiptLine(Base):
    __tablename__ = "inbound_receipt_lines"

    __table_args__ = (
        CheckConstraint(
            "(production_date IS NULL) OR (expiry_date IS NULL) OR (production_date <= expiry_date)",
            name="ck_inbound_receipt_lines_prod_le_exp",
        ),
        CheckConstraint(
            "qty_base = (qty_input * ratio_to_base_snapshot)",
            name="ck_receipt_qty_base_consistent",
        ),
        sa.UniqueConstraint(
            "receipt_id",
            "line_no",
            name="uq_inbound_receipt_lines_receipt_line",
        ),
        {"info": {"skip_autogen": True}},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    receipt_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inbound_receipts.id", name="fk_inbound_receipt_lines_receipt", ondelete="CASCADE"),
        nullable=False,
    )

    line_no: Mapped[int] = mapped_column(Integer, nullable=False)

    po_line_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("purchase_order_lines.id", name="fk_inbound_receipt_lines_po_line", ondelete="SET NULL"),
        nullable=True,
    )

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", name="fk_inbound_receipt_lines_item", ondelete="RESTRICT"),
        nullable=False,
    )

    # 新字段：供应商批次输入
    lot_code_input: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    lot_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    receipt_status_snapshot: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DRAFT",
    )

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", name="fk_inbound_receipt_lines_warehouse", ondelete="RESTRICT"),
        nullable=False,
    )

    production_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)

    uom_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("item_uoms.id", name="fk_receipt_line_uom"),
        nullable=False,
    )

    qty_input: Mapped[int] = mapped_column(Integer, nullable=False)
    ratio_to_base_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_base: Mapped[int] = mapped_column(Integer, nullable=False)

    unit_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    line_amount: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)

    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    receipt: Mapped["InboundReceipt"] = relationship(
        "InboundReceipt",
        back_populates="lines",
    )
