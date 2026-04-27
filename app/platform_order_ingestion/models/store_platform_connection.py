# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/models/store_platform_connection.py
# Domain move: store platform connection ORM belongs to OMS platform access.
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StorePlatformConnection(Base):
    """
    店铺 × 平台 当前接入状态表（当前态）。

    职责：
    - 保存 OMS 对当前接入状态的业务裁决
    - 保存是否需要重授权、是否 pull_ready、当前状态与原因
    - 不保存 access_token / refresh_token 等授权材料
    """

    __tablename__ = "store_platform_connections"

    __table_args__ = (
        sa.UniqueConstraint(
            "store_id",
            "platform",
            name="uq_store_platform_connections_store_platform",
        ),
        sa.Index(
            "ix_store_platform_connections_platform",
            "platform",
        ),
        sa.Index(
            "ix_store_platform_connections_status",
            "status",
        ),
        sa.Index(
            "ix_store_platform_connections_pull_ready",
            "pull_ready",
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

    auth_source: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=sa.text("'none'"),
    )

    connection_status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=sa.text("'not_connected'"),
    )

    credential_status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=sa.text("'missing'"),
    )

    reauth_required: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.false(),
    )

    pull_ready: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.false(),
    )

    status: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        server_default=sa.text("'not_connected'"),
    )

    status_reason: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
    )

    last_authorized_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    last_pull_checked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    last_error_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
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
