from __future__ import annotations

from datetime import datetime
from sqlalchemy import String, Integer, BigInteger, TIMESTAMP, Text, UniqueConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformShop(Base):
    __tablename__ = "platform_shops"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    shop_id: Mapped[str] = mapped_column(String(64), nullable=False)

    access_token: Mapped[str | None] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)  # ACTIVE/PAUSED/REVOKED
    rate_limit_qps: Mapped[int | None] = mapped_column(Integer, default=5)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("platform", "shop_id", name="uq_platform_shops_platform_shop"),
        Index("ix_platform_shops_status", "status"),
    )
