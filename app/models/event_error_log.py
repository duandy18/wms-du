from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventErrorLog(Base):
    __tablename__ = "event_error_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_no: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)

    from_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)

    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    error_msg: Mapped[str | None] = mapped_column(String(512), nullable=True)

    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_event_error_log_key", "platform", "shop_id", "idempotency_key"),
        Index("ix_event_error_log_retry", "next_retry_at"),
    )
