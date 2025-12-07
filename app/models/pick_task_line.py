# app/models/pick_task_line.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .pick_task import PickTask


def _PickTask() -> "PickTask":
    from .pick_task import PickTask

    return PickTask


class PickTaskLine(Base):
    __tablename__ = "pick_task_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pick_tasks.id"),
        nullable=False,
    )
    order_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    order_line_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    req_qty: Mapped[int] = mapped_column(BigInteger, nullable=False)
    picked_qty: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )

    batch_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    prefer_pickface: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    target_location_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'NEW'"),
    )
    note: Mapped[Optional[str]] = mapped_column(Text)

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

    task: Mapped["PickTask"] = relationship(
        _PickTask,
        back_populates="lines",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_pick_task_lines_item", "item_id"),
        Index("ix_pick_task_lines_status", "status"),
        Index("ix_pick_task_lines_task", "task_id"),
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return (
            f"<PickTaskLine id={self.id} item={self.item_id} "
            f"req={self.req_qty} picked={self.picked_qty} "
            f"batch={self.batch_code} status={self.status}>"
        )
