# app/models/inbound_receipt.py
from __future__ import annotations

from datetime import datetime, date as date_type
from typing import List, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InboundReceipt(Base):
    """
    终态收货单模型（唯一事实表）

    - 草稿与确认通过 status 区分
    - 不再依赖 receive_task
    """

    __tablename__ = "inbound_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    supplier_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
    )
    supplier_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # 事实来源
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # PO / OTHER
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 唯一单据标识
    ref: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # DRAFT / CONFIRMED / CANCELLED
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    receipt_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inbound_receipts.id", ondelete="CASCADE"),
        nullable=False,
    )

    line_no: Mapped[int] = mapped_column(Integer, nullable=False)

    po_line_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("purchase_order_lines.id", ondelete="SET NULL"),
        nullable=True,
    )

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
    )

    item_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    item_sku: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    spec_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    base_uom: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    purchase_uom: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    batch_code: Mapped[str] = mapped_column(String(64), nullable=False)
    production_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)

    qty_received: Mapped[int] = mapped_column(Integer, nullable=False)
    units_per_case: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    qty_units: Mapped[int] = mapped_column(Integer, nullable=False)

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
