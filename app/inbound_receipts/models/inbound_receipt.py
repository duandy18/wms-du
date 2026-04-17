# app/inbound_receipts/models/inbound_receipt.py
# 拆分说明：
# 本文件承接“入库任务层”ORM 模型，只负责 inbound_receipts / inbound_receipt_lines。
# 它位于 procurement 与 WMS 之间的独立模块，不再沿用旧 app/wms/inbound/models/inbound_receipt.py 的混合语义。
from __future__ import annotations

from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InboundReceipt(Base):
    __tablename__ = "inbound_receipts"

    __table_args__ = (
        UniqueConstraint("receipt_no", name="uq_inbound_receipts_receipt_no"),
        CheckConstraint(
            "source_type IN ('PURCHASE_ORDER', 'MANUAL', 'RETURN_ORDER')",
            name="ck_inbound_receipts_source_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'RELEASED', 'VOIDED')",
            name="ck_inbound_receipts_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    receipt_no: Mapped[str] = mapped_column(String(64), nullable=False)

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_doc_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_doc_no_snapshot: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", name="fk_inbound_receipts_warehouse", ondelete="RESTRICT"),
        nullable=False,
    )
    warehouse_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    supplier_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", name="fk_inbound_receipts_supplier", ondelete="RESTRICT"),
        nullable=True,
    )
    counterparty_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT", server_default="DRAFT")
    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_inbound_receipts_created_by", ondelete="SET NULL"),
        nullable=True,
    )
    released_at: Mapped[Optional[DateTime]] = mapped_column(DateTime(timezone=True), nullable=True)

    lines: Mapped[list["InboundReceiptLine"]] = relationship(
        "InboundReceiptLine",
        back_populates="receipt",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class InboundReceiptLine(Base):
    __tablename__ = "inbound_receipt_lines"

    __table_args__ = (
        UniqueConstraint(
            "inbound_receipt_id",
            "line_no",
            name="uq_inbound_receipt_lines_receipt_line",
        ),
        CheckConstraint(
            "planned_qty > 0",
            name="ck_inbound_receipt_lines_planned_qty_positive",
        ),
        CheckConstraint(
            "ratio_to_base_snapshot > 0",
            name="ck_inbound_receipt_lines_ratio_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    inbound_receipt_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inbound_receipts.id", name="fk_inbound_receipt_lines_receipt", ondelete="CASCADE"),
        nullable=False,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)

    source_line_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", name="fk_inbound_receipt_lines_item", ondelete="RESTRICT"),
        nullable=False,
    )
    item_uom_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("item_uoms.id", name="fk_inbound_receipt_lines_item_uom", ondelete="RESTRICT"),
        nullable=False,
    )

    planned_qty: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    item_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    item_spec_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    uom_name_snapshot: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ratio_to_base_snapshot: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    receipt: Mapped["InboundReceipt"] = relationship(
        "InboundReceipt",
        back_populates="lines",
    )


__all__ = [
    "InboundReceipt",
    "InboundReceiptLine",
]
