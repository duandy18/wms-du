# app/oms/platforms/models/pdd_app_config.py
# Domain move: PDD app config ORM belongs to OMS platform access.
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PddAppConfig(Base):
    """
    拼多多开放平台系统级应用配置表。

    职责：
    - 保存 OMS 系统接入拼多多开放平台所需的应用配置
    - 保存 client_id / client_secret / redirect_uri / api_base_url / sign_method
    - 保存当前是否启用的配置记录

    不负责：
    - 店铺授权材料（access_token / refresh_token）
    - 店铺接入状态裁决
    - 店铺 identity
    """

    __tablename__ = "pdd_app_configs"

    __table_args__ = (
        sa.Index(
            "ix_pdd_app_configs_is_enabled",
            "is_enabled",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    client_id: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
    )

    client_secret: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    redirect_uri: Mapped[str] = mapped_column(
        sa.String(512),
        nullable=False,
    )

    api_base_url: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        server_default=sa.text("'https://gw-api.pinduoduo.com/api/router'"),
    )

    sign_method: Mapped[str] = mapped_column(
        sa.String(16),
        nullable=False,
        server_default=sa.text("'md5'"),
    )

    is_enabled: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.false(),
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
