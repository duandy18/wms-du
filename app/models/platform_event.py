from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformEvent(Base):
    __tablename__ = "platform_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    shop_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NEW'"))

    # ★ 统一为 JSONB
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    dedup_key: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # 若 DB 是 identity/计算列，保持 nullable 一致
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
