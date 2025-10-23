# app/models/event_error_log.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Integer, JSON, TIMESTAMP, text, Index
from sqlalchemy.orm import Mapped, mapped_column

# ⚠️ 结合你的项目基类路径引入 Base（这是你原文件缺失的一行）
from app.db.base import Base


class EventErrorLog(Base):
    __tablename__ = "event_error_log"

    id: Mapped[int] = mapped_column(primary_key=True)

    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_no: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)

    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)

    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    error_msg: Mapped[str | None]
    payload_json: Mapped[dict | None] = mapped_column(JSON)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# 索引（与你现有风格一致，保留模块级定义）
Index(
    "ix_event_error_log_key",
    EventErrorLog.platform,
    EventErrorLog.shop_id,
    EventErrorLog.idempotency_key,
)
Index(
    "ix_event_error_log_retry",
    EventErrorLog.next_retry_at,
    postgresql_where=text("retry_count < max_retries"),
)
