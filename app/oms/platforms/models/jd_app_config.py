# app/oms/platforms/models/jd_app_config.py
# Domain move: JD app config ORM belongs to OMS platform access.
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class JdAppConfig(Base):
    """
    京东平台系统级接入配置（当前态）。

    职责：
    - 保存 JD OAuth / JOS 所需系统级配置
    - 不保存店铺级 access_token / refresh_token
    - 不承载 OMS connection / pull_ready 等业务状态
    """

    __tablename__ = "jd_app_configs"

    __table_args__ = (
        sa.Index(
            "ix_jd_app_configs_is_enabled",
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

    callback_url: Mapped[str] = mapped_column(
        sa.String(512),
        nullable=False,
    )

    gateway_url: Mapped[str] = mapped_column(
        sa.String(512),
        nullable=False,
        server_default=sa.text("'https://api.jd.com/routerjson'"),
    )

    sign_method: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=sa.text("'md5'"),
    )

    is_enabled: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.true(),
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
