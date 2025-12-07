from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformShop(Base):
    __tablename__ = "platform_shops"

    # DB 侧 id 为 BIGINT，这里对齐为 BigInteger
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="平台类型（PDD/TAOBAO/JD 等）",
    )
    # shop_id: varchar(64) -> varchar(128) + 注释
    shop_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="平台店铺唯一 ID",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'ACTIVE'"),
    )
    # rate_limit_qps: NOT NULL + 默认值
    rate_limit_qps: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        # 为避免与 stores 上的索引名称冲突，这里使用更明确的名字
        Index("ix_platform_shops_shop_id", "shop_id"),
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"<PlatformShop id={self.id} platform={self.platform} shop_id={self.shop_id}>"
