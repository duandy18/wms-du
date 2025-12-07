from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventLog(Base):
    __tablename__ = "event_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'INFO'"))
    source: Mapped[str | None] = mapped_column(Text, nullable=True)

    message: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    meta: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, server_default=text("'{}'::jsonb")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_event_log_level", "level"),
        Index("ix_event_log_source", "source"),
        Index("ix_event_log_time", "occurred_at"),
        {"info": {"skip_autogen": True}},
    )
