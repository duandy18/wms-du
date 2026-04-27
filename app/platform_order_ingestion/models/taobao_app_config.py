# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
# app/platform_order_ingestion/models/taobao_app_config.py
# Domain move: Taobao app config ORM belongs to OMS platform access.
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaobaoAppConfig(Base):
    """
    淘宝开放平台系统级应用配置表。

    职责：
    - 保存 OMS 系统接入淘宝开放平台所需的应用配置
    - 保存 app_key / app_secret / callback_url / api_base_url / sign_method
    - 保存当前是否启用的配置记录

    不负责：
    - 店铺授权材料（access_token / refresh_token）
    - 店铺接入状态裁决
    - 店铺 identity
    """

    __tablename__ = "taobao_app_configs"

    __table_args__ = (
        sa.Index(
            "ix_taobao_app_configs_is_enabled",
            "is_enabled",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    app_key: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
    )

    app_secret: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    callback_url: Mapped[str] = mapped_column(
        sa.String(512),
        nullable=False,
    )

    api_base_url: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        server_default=sa.text("'https://eco.taobao.com/router/rest'"),
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
