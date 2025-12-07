from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventStore(Base):
    """事件存储 event_store（以数据库为准）"""

    __tablename__ = "event_store"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    key: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    headers: Mapped[dict | None] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    # Phase 3.7：trace_id 成为跨表 trace 主键；为空时表示老数据或非链路事件
    trace_id: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_event_store_topic", "topic"),
        Index("ix_event_store_status", "status"),
        Index("ix_event_store_occurred", "occurred_at"),
        # 使用 skip_autogen 避免 Alembic 自动生成 diff（以手工迁移为准）
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return f"<EventStore id={self.id} topic={self.topic} status={self.status}>"
