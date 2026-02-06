# app/models/platform_sku_binding.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformSkuBinding(Base):
    __tablename__ = "platform_sku_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # 平台侧唯一键（S1）
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    shop_id: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_sku_id: Mapped[str] = mapped_column(String(200), nullable=False)

    # 绑定目标（二选一，由 DB 的 CHECK 约束保证 XOR）
    # 单品：item_id
    # 组合：fsku_id
    fsku_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("fskus.id"),  # ⚠️ 不写 ondelete，保持与当前 DB 一致
        nullable=True,
    )
    item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("items.id", ondelete="RESTRICT"),  # ✅ 与 DB 中 FK 完全一致
        nullable=True,
    )

    # 生效语义：current = effective_to IS NULL
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 审计说明
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# 查询索引（非唯一）
Index(
    "ix_platform_sku_bindings_key",
    PlatformSkuBinding.platform,
    PlatformSkuBinding.shop_id,
    PlatformSkuBinding.platform_sku_id,
)

# ✅ current 唯一（同一个 platform + shop + sku，在任意时刻只能有一条生效记录）
Index(
    "ux_platform_sku_bindings_current",
    PlatformSkuBinding.platform,
    PlatformSkuBinding.shop_id,
    PlatformSkuBinding.platform_sku_id,
    unique=True,
    postgresql_where=PlatformSkuBinding.effective_to.is_(None),
)
