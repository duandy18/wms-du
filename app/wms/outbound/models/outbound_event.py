# app/wms/outbound/models/outbound_event.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, CheckConstraint, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboundEventLine(Base):
    """
    出库事件行：
    - 头表复用 wms_events
    - 本表只记录本次出库提交的行级事实
    """
    __tablename__ = "outbound_event_lines"
    __table_args__ = (
        CheckConstraint("qty_outbound > 0", name="ck_outbound_event_lines_qty_positive"),
        CheckConstraint(
            """
            (order_line_id IS NOT NULL AND manual_doc_line_id IS NULL)
            OR
            (order_line_id IS NULL AND manual_doc_line_id IS NOT NULL)
            """,
            name="ck_outbound_event_lines_source_oneof",
        ),
        UniqueConstraint("event_id", "ref_line", name="uq_outbound_event_lines_event_ref_line"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("wms_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    ref_line: Mapped[int] = mapped_column(Integer, nullable=False)

    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_outbound: Mapped[int] = mapped_column(Integer, nullable=False)

    lot_id: Mapped[int] = mapped_column(Integer, nullable=False)
    lot_code_snapshot: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    order_line_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("order_lines.id", ondelete="RESTRICT"),
        nullable=True,
    )
    manual_doc_line_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )

    item_name_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    item_spec_snapshot: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
