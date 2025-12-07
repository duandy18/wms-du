# app/models/store_token.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

# 关键：你项目里 Base 在 app.db.base 里
from app.db.base import Base


class StoreToken(Base):
    """
    第三方平台授权令牌（目前主要是 PDD）。

    一条记录 ≈ 某个 store 在某个平台上的一份长期授权。
    """

    __tablename__ = "store_tokens"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)

    # 关联内部店铺（stores 表）
    store_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 平台标识：如 "pdd" / "tb" / "jd"
    platform: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True)

    # 平台侧店铺 ID（例如 PDD 的 mall_id / owner_id），冗余方便排查
    mall_id: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)

    access_token: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    refresh_token: Mapped[str] = mapped_column(sa.String(255), nullable=False)

    scope: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)

    # token 过期时间（绝对时间）
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)

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

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if now is None:
            now = datetime.now(timezone.utc)
        return now >= self.expires_at
