# app/models/event_error_log.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Integer, JSON, TIMESTAMP, text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base  # 保持与你项目的 Base 路径一致


class EventErrorLog(Base):
    """
    平台事件错误日志：
    - 幂等键：platform + shop_id + idempotency_key（索引见下）
    - 重试机制：retry_count / max_retries / next_retry_at
    - 时间列具时区；DB 层存 UTC
    """
    __tablename__ = "event_error_log"

    id: Mapped[int] = mapped_column(primary_key=True)

    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_no: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)

    from_state: Mapped[str | None] = mapped_column(String(32))
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)

    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    error_msg: Mapped[str | None] = mapped_column(String(512))
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


# 索引（模块级定义，跨方言更直观）
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
