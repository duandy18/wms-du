# app/wms/inbound_operations/models/inbound_operation.py
# 拆分说明：
# 本文件承接“WMS 收货操作事实层”ORM 模型，只负责
# wms_inbound_operations / wms_inbound_operation_lines。
# 它是围绕入库任务号的多次实际收货记录，不再复用旧一层式 inbound_event 提交模型。
from __future__ import annotations

from datetime import date as date_type, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WmsInboundOperation(Base):
    __tablename__ = "wms_inbound_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    receipt_no_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", name="fk_wms_inbound_operations_warehouse", ondelete="RESTRICT"),
        nullable=False,
    )
    warehouse_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    supplier_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("suppliers.id", name="fk_wms_inbound_operations_supplier", ondelete="RESTRICT"),
        nullable=True,
    )
    supplier_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    operator_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_wms_inbound_operations_operator", ondelete="SET NULL"),
        nullable=True,
    )
    operator_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    operated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    lines: Mapped[list["WmsInboundOperationLine"]] = relationship(
        "WmsInboundOperationLine",
        back_populates="operation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WmsInboundOperationLine(Base):
    __tablename__ = "wms_inbound_operation_lines"

    __table_args__ = (
        CheckConstraint(
            "(production_date IS NULL) OR (expiry_date IS NULL) OR (production_date <= expiry_date)",
            name="ck_wms_inbound_operation_lines_prod_le_exp",
        ),
        CheckConstraint(
            "ratio_to_base_snapshot > 0",
            name="ck_wms_inbound_operation_lines_ratio_positive",
        ),
        CheckConstraint(
            "qty_inbound > 0",
            name="ck_wms_inbound_operation_lines_qty_inbound_positive",
        ),
        CheckConstraint(
            "qty_base > 0",
            name="ck_wms_inbound_operation_lines_qty_base_positive",
        ),
        CheckConstraint(
            "qty_base = (qty_inbound * ratio_to_base_snapshot)",
            name="ck_wms_inbound_operation_lines_qty_base_consistent",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    wms_inbound_operation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "wms_inbound_operations.id",
            name="fk_wms_inbound_operation_lines_operation",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    receipt_line_no_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", name="fk_wms_inbound_operation_lines_item", ondelete="RESTRICT"),
        nullable=False,
    )
    item_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    item_spec_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    item_uom_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("item_uoms.id", name="fk_wms_inbound_operation_lines_item_uom", ondelete="RESTRICT"),
        nullable=False,
    )
    uom_name_snapshot: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ratio_to_base_snapshot: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    qty_inbound: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    qty_base: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)

    batch_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    production_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)

    lot_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("lots.id", name="fk_wms_inbound_operation_lines_lot", ondelete="RESTRICT"),
        nullable=True,
    )

    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    operation: Mapped["WmsInboundOperation"] = relationship(
        "WmsInboundOperation",
        back_populates="lines",
    )


__all__ = [
    "WmsInboundOperation",
    "WmsInboundOperationLine",
]
