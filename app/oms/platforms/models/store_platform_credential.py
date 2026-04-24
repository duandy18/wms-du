# app/oms/platforms/models/store_platform_credential.py
# Domain move: store platform credential ORM belongs to OMS platform access.
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StorePlatformCredential(Base):
    """
    店铺 × 平台 当前授权材料表（当前态）。

    职责：
    - 保存平台返回的授权材料
    - 保存授权回包里自带的基础身份线索
    - 不承载 OMS 的 connection / pull_ready / 状态裁决
    """

    __tablename__ = "store_platform_credentials"

    __table_args__ = (
        sa.UniqueConstraint(
            "store_id",
            "platform",
            name="uq_store_platform_credentials_store_platform",
        ),
        sa.Index(
            "ix_store_platform_credentials_platform",
            "platform",
        ),
        sa.Index(
            "ix_store_platform_credentials_expires_at",
            "expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    store_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )

    platform: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
    )

    credential_type: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=sa.text("'oauth'"),
    )

    access_token: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    refresh_token: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    scope: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )

    raw_payload_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    granted_identity_type: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )

    granted_identity_value: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
    )

    granted_identity_display: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
