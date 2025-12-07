# app/services/store_token_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store_token import StoreToken


@dataclass
class TokenRecord:
    platform: str
    store_id: int
    mall_id: Optional[str]
    access_token: str
    expires_at: datetime
    source: str  # "store_tokens" / "platform_shops"


class StoreTokenNotFound(Exception):
    """指定 store/platform 没有任何 token 记录。"""


class StoreTokenExpired(Exception):
    """token 已过期。"""


class StoreTokenService:
    """
    统一的 Token 供应站：

    - 优先从 store_tokens 取 OAuth token（我们新建的那张表）
    - 取不到时，可选地从 platform_shops 兜底（你之前的手工凭据表）
    - 以后所有 PDD / TB / JD HTTP 调用，都应该走这里拿 token
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_token_for_store(
        self,
        store_id: int,
        platform: str,
        allow_fallback: bool = True,
        now: Optional[datetime] = None,
    ) -> TokenRecord:
        platform = platform.lower()
        if now is None:
            now = datetime.now(timezone.utc)

        # 1) 优先查 OAuth 正规来源：store_tokens
        stmt = (
            sa.select(StoreToken)
            .where(
                StoreToken.store_id == store_id,
                StoreToken.platform == platform,
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        row: Optional[StoreToken] = result.scalar_one_or_none()

        if row:
            if row.expires_at <= now:
                raise StoreTokenExpired(
                    f"store_id={store_id}, platform={platform} token 已过期，请重新授权"
                )
            return TokenRecord(
                platform=platform,
                store_id=store_id,
                mall_id=row.mall_id,
                access_token=row.access_token,
                expires_at=row.expires_at,
                source="store_tokens",
            )

        # 2) 看需不需要从 platform_shops 兜底（老逻辑 / 手工录入）
        if not allow_fallback:
            raise StoreTokenNotFound(f"store_id={store_id}, platform={platform} 未找到 OAuth token")

        # 先根据 store_id 找出 (platform, shop_id)
        result = await self.db.execute(
            text(
                """
                SELECT s.platform, s.shop_id
                FROM stores AS s
                WHERE s.id = :store_id
                """
            ),
            {"store_id": store_id},
        )
        store_row = result.mappings().first()
        if not store_row:
            raise StoreTokenNotFound(f"store_id={store_id} 不存在")

        plat_upper = (store_row["platform"] or "").upper()
        shop_id = store_row["shop_id"]

        # 再查 platform_shops 表
        try:
            result2 = await self.db.execute(
                text(
                    """
                    SELECT access_token, token_expires_at
                    FROM platform_shops
                    WHERE platform = :p AND shop_id = :s
                    """
                ),
                {"p": plat_upper, "s": shop_id},
            )
            cred = result2.mappings().first()
        except Exception:
            cred = None

        if not cred or not cred["access_token"]:
            raise StoreTokenNotFound(
                f"store_id={store_id}, platform={platform} 未找到任何 token "
                "(store_tokens / platform_shops 都没有)"
            )

        expires_at = cred["token_expires_at"] or (now + timedelta(hours=2))
        if expires_at <= now:
            raise StoreTokenExpired(
                f"store_id={store_id}, platform={platform} 手工 token 已过期，请更新 credentials"
            )

        return TokenRecord(
            platform=platform,
            store_id=store_id,
            mall_id=None,
            access_token=cred["access_token"],
            expires_at=expires_at,
            source="platform_shops",
        )
