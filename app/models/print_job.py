# app/models/print_job.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PrintJob(Base):
    """
    打印任务（幂等入队 + 状态回写）：

    表结构来自 DB：
      - id bigint pk
      - kind / ref_type / ref_id：幂等唯一键 uq_print_jobs_pick_list_ref (kind, ref_type, ref_id)
      - status：queued / printed / failed（当前表 default 'queued'）
      - payload：jsonb（必须非空）
      - requested_at：入队时间
      - printed_at：打印完成时间（可空）
      - error：失败原因（可空）
      - created_at / updated_at
    """

    __tablename__ = "print_jobs"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)

    kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    ref_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    ref_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)

    status: Mapped[str] = mapped_column(sa.Text, nullable=False, server_default=sa.text("'queued'"))

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    requested_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    printed_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.Index("ix_print_jobs_kind", "kind"),
        sa.Index("ix_print_jobs_status", "status"),
        sa.UniqueConstraint("kind", "ref_type", "ref_id", name="uq_print_jobs_pick_list_ref"),
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return f"<PrintJob id={self.id} kind={self.kind} status={self.status} ref={self.ref_type}:{self.ref_id}>"
