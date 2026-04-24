# app/wms/inbound/models/inbound_event.py
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from typing import List, Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


_EVENT_TYPES = (
    "INBOUND",
    "OUTBOUND",
    "COUNT",
)

_SOURCE_TYPES = (
    "PURCHASE_ORDER",
    "MANUAL",
    "RETURN",
    "TRANSFER_IN",
    "ADJUST_IN",
    "ORDER",
    "ORDER_SHIP",
    "INTERNAL_OUTBOUND",
    "TRANSFER_OUT",
    "SCRAP",
    "ADJUST_OUT",
    "COUNT_TASK",
    "MANUAL_COUNT",
)

_EVENT_KINDS = (
    "COMMIT",
    "REVERSAL",
    "CORRECTION",
)

_EVENT_STATUSES = (
    "COMMITTED",
    "VOIDED",
    "SUPERSEDED",
)


class WmsEvent(Base):
    __tablename__ = "wms_events"

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('INBOUND', 'OUTBOUND', 'COUNT')",
            name="ck_wms_events_event_type",
        ),
        CheckConstraint(
            (
                "source_type IN ("
                "'PURCHASE_ORDER', 'MANUAL', 'RETURN', 'TRANSFER_IN', 'ADJUST_IN', "
                "'ORDER', 'ORDER_SHIP', 'INTERNAL_OUTBOUND', 'TRANSFER_OUT', 'SCRAP', 'ADJUST_OUT', "
                "'COUNT_TASK', 'MANUAL_COUNT'"
                ")"
            ),
            name="ck_wms_events_source_type",
        ),
        CheckConstraint(
            "event_kind IN ('COMMIT', 'REVERSAL', 'CORRECTION')",
            name="ck_wms_events_event_kind",
        ),
        CheckConstraint(
            "status IN ('COMMITTED', 'VOIDED', 'SUPERSEDED')",
            name="ck_wms_events_status",
        ),
        UniqueConstraint("event_no", name="uq_wms_events_event_no"),
        UniqueConstraint("trace_id", name="uq_wms_events_trace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_no: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.id", name="fk_wms_events_warehouse", ondelete="RESTRICT"),
        nullable=False,
    )

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)

    event_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="COMMIT",
        server_default="COMMIT",
    )

    target_event_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("wms_events.id", name="fk_wms_events_target_event", ondelete="RESTRICT"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="COMMITTED",
        server_default="COMMITTED",
    )

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", name="fk_wms_events_created_by", ondelete="SET NULL"),
        nullable=True,
    )

    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    inbound_lines: Mapped[List["InboundEventLine"]] = relationship(
        "InboundEventLine",
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    target_event: Mapped[Optional["WmsEvent"]] = relationship(
        "WmsEvent",
        remote_side="WmsEvent.id",
        foreign_keys=[target_event_id],
        lazy="selectin",
    )


class InboundEventLine(Base):
    __tablename__ = "inbound_event_lines"

    __table_args__ = (
        CheckConstraint(
            "(production_date IS NULL) OR (expiry_date IS NULL) OR (production_date <= expiry_date)",
            name="ck_inbound_event_lines_prod_le_exp",
        ),
        CheckConstraint(
            "actual_ratio_to_base_snapshot >= 1",
            name="ck_inbound_event_lines_actual_ratio_positive",
        ),
        CheckConstraint(
            "actual_qty_input >= 1",
            name="ck_inbound_event_lines_actual_qty_input_positive",
        ),
        CheckConstraint(
            "qty_base = (actual_qty_input * actual_ratio_to_base_snapshot)",
            name="ck_inbound_event_lines_actual_qty_base_consistent",
        ),
        UniqueConstraint(
            "event_id",
            "line_no",
            name="uq_inbound_event_lines_event_line",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wms_events.id", name="fk_inbound_event_lines_event", ondelete="CASCADE"),
        nullable=False,
    )

    line_no: Mapped[int] = mapped_column(Integer, nullable=False)

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("items.id", name="fk_inbound_event_lines_item", ondelete="RESTRICT"),
        nullable=False,
    )

    item_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    item_spec_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    actual_uom_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("item_uoms.id", name="fk_inbound_event_lines_actual_uom", ondelete="RESTRICT"),
        nullable=False,
    )
    actual_uom_name_snapshot: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    barcode_input: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    actual_qty_input: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_ratio_to_base_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_base: Mapped[int] = mapped_column(Integer, nullable=False)

    lot_code_input: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    production_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)

    lot_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("lots.id", name="fk_inbound_event_lines_lot", ondelete="RESTRICT"),
        nullable=True,
    )

    po_line_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("purchase_order_lines.id", name="fk_inbound_event_lines_po_line", ondelete="SET NULL"),
        nullable=True,
    )

    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    event: Mapped["WmsEvent"] = relationship(
        "WmsEvent",
        back_populates="inbound_lines",
    )


__all__ = [
    "WmsEvent",
    "InboundEventLine",
]
