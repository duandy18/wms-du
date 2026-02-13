from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, Text, Enum, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from .pick_task_line import PickTaskLine


def _PickTaskLine() -> "PickTaskLine":
    from .pick_task_line import PickTaskLine

    return PickTaskLine


class PickTask(Base):
    __tablename__ = "pick_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ✅ Phase 3：scope（PROD/DRILL）作业宇宙隔离
    scope: Mapped[str] = mapped_column(
        Enum("PROD", "DRILL", name="biz_scope"),
        nullable=False,
        comment="作业 scope（PROD/DRILL）。DRILL 与 PROD 作业宇宙隔离。",
    )

    warehouse_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text)
    ref: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    assigned_to: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NEW'"))
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    lines: Mapped[List["PickTaskLine"]] = relationship(
        _PickTaskLine,
        back_populates="task",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_pick_tasks_assigned", "assigned_to"),
        Index("ix_pick_tasks_status", "status"),
        Index("ix_pick_tasks_wh_prio", "warehouse_id", "priority"),
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return (
            f"<PickTask id={self.id} "
            f"scope={getattr(self, 'scope', None)} "
            f"wh={getattr(self, 'timezone', None) or self.warehouse_id} "
            f"status={self.status}>"
        )
