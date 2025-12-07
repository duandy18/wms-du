from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    """
    审计事件表 audit_events（以数据库为准）

    字段（当前 DB）：
      - id: BIGINT 主键
      - category: VARCHAR(64) NOT NULL
      - ref: VARCHAR(128) NOT NULL
      - trace_id: VARCHAR(64) NULL   ← 用于跨表 trace 聚合
      - created_at: timestamptz NOT NULL DEFAULT now()
      - meta: JSONB NOT NULL
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    ref: Mapped[str] = mapped_column(String(128), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        # 历史索引，与现网一致，避免 autogen 误差
        Index("ix_audit_events_category", "category"),
        Index("ix_audit_events_outbound_ref_time", "ref", "created_at"),
        Index("ix_audit_events_cat_ref_time", "category", "ref", "created_at"),
        Index("ix_audit_events_ref", "ref"),
        # 新增 trace_id 索引（与 p42 迁移对齐）
        Index("ix_audit_events_trace_id", "trace_id"),
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return (
            f"<AuditEvent id={self.id} category={self.category} "
            f"ref={self.ref} trace_id={self.trace_id}>"
        )
