# app/models/platform_shops.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Integer,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base  # 若你的基类路径不同，请保持与你项目一致


class PlatformShop(Base):
    """
    平台店铺信息表（强契约·现代声明式）
    - 与现有表结构完全一致（无需 Alembic 迁移）
    - 用于存储各电商平台授权店铺的凭据和状态
    - UTC 时间入库，展示层转换 Asia/Shanghai(+08:00)
    """

    __tablename__ = "platform_shops"
    __table_args__ = (
        UniqueConstraint("platform", "shop_id", name="uq_platform_shops_platform_shop"),
        Index("ix_platform_shops_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 平台信息
    platform: Mapped[str] = mapped_column(String(32), nullable=False, comment="平台类型，如 pdd/tb/jd")
    shop_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="平台店铺唯一 ID")

    # 授权凭据
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, comment="token 过期时间(UTC)"
    )

    # 状态与限流配置
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", comment="ACTIVE/PAUSED/REVOKED")
    rate_limit_qps: Mapped[int] = mapped_column(Integer, nullable=False, default=5, comment="平台 API 限流QPS")

    # 具时区时间：存库为 UTC，展示层转 Asia/Shanghai(+8)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, comment="创建时间(UTC)"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, comment="更新时间(UTC)"
    )

    def __repr__(self) -> str:
        return (
            f"<PlatformShop id={self.id} platform={self.platform!r} "
            f"shop_id={self.shop_id!r} status={self.status}>"
        )
