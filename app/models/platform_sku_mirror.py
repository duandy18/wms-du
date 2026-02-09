# app/models/platform_sku_mirror.py
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformSkuMirror(Base):
    __tablename__ = "platform_sku_mirror"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    platform: Mapped[str] = mapped_column(String(50), nullable=False)

    # ✅ 内部店铺主键：stores.id（DB 当前是 bigint，这里保持一致）
    # ✅ 与迁移 a0a0e1e9ad09 建立的 FK 对齐（RESTRICT）
    store_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("stores.id", ondelete="RESTRICT"),
        nullable=False,
    )

    platform_sku_id: Mapped[str] = mapped_column(String(200), nullable=False)

    sku_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    spec: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    source: Mapped[str] = mapped_column(String(50), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("platform", "store_id", "platform_sku_id", name="ux_platform_sku_mirror_key"),
    )
