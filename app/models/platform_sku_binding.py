# app/models/platform_sku_binding.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformSkuBinding(Base):
    __tablename__ = "platform_sku_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    shop_id: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_sku_id: Mapped[str] = mapped_column(String(200), nullable=False)

    fsku_id: Mapped[int] = mapped_column(Integer, ForeignKey("fskus.id"), nullable=False)

    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# 查询索引
Index(
    "ix_platform_sku_bindings_key",
    PlatformSkuBinding.platform,
    PlatformSkuBinding.shop_id,
    PlatformSkuBinding.platform_sku_id,
)

# ✅ current 唯一（同 key 只能有一条 effective_to IS NULL）
Index(
    "ux_platform_sku_bindings_current",
    PlatformSkuBinding.platform,
    PlatformSkuBinding.shop_id,
    PlatformSkuBinding.platform_sku_id,
    unique=True,
    postgresql_where=PlatformSkuBinding.effective_to.is_(None),
)
