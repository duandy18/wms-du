# app/api/routers/platform_shops_routes_tokens.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.platform_shops_helpers import audit, mask
from app.api.routers.platform_shops_schemas import PlatformShopCredentialsIn, SimpleOut
from app.models.store import Store
from app.models.store_token import StoreToken
from app.services.store_service import StoreService


def register(router: APIRouter) -> None:
    # ---------------------------------------------------------------------------
    # 1) 手工录入 / 更新 平台店铺凭据  -> 直接写入 store_tokens
    #    POST /platform-shops/credentials
    # ---------------------------------------------------------------------------

    @router.post("/platform-shops/credentials", response_model=SimpleOut)
    async def upsert_credentials(
        body: PlatformShopCredentialsIn,
        session: AsyncSession = Depends(get_session),
    ) -> SimpleOut:
        """
        手工录入平台店铺 access_token（不走 OAuth，快速调试用）。

        行为调整版（相比旧实现）：
        - 不再写 legacy 的 platform_shops 表；
        - 统一写入 store_tokens 表，和 OAuth token 走同一套模型；
        - refresh_token 固定为 "MANUAL"，方便区分来源。
        """
        plat_upper = body.platform.upper()
        plat_lower = body.platform.lower()
        shop_id = body.shop_id

        # 1) 确保内部 store 档案存在，并拿到 store_id
        store_id = await StoreService.ensure_store(
            session,
            platform=plat_upper,
            shop_id=shop_id,
            name=body.store_name,
        )

        # 2) 计算过期时间（默认 2 小时后）
        now = datetime.now(timezone.utc)
        expires_at = body.token_expires_at or (now + timedelta(hours=2))

        # 3) upsert store_tokens
        result = await session.execute(
            select(StoreToken).where(
                StoreToken.store_id == store_id,
                StoreToken.platform == plat_lower,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.access_token = body.access_token
            existing.refresh_token = "MANUAL"
            existing.expires_at = expires_at
            token_row = existing
        else:
            token_row = StoreToken(
                store_id=store_id,
                platform=plat_lower,
                mall_id=None,
                access_token=body.access_token,
                refresh_token="MANUAL",
                expires_at=expires_at,
            )
            session.add(token_row)

        await session.commit()
        await session.refresh(token_row)

        await audit(
            session,
            ref=f"PLATFORM_CRED:{plat_upper}:{shop_id}",
            meta={
                "event": "UPSERT_CREDENTIALS",
                "token_expires_at": expires_at.isoformat(),
                "status": body.status or "ACTIVE",
                "store_id": store_id,
                "source": "MANUAL",
            },
        )

        return SimpleOut(
            ok=True,
            data={
                "platform": plat_upper,
                "shop_id": shop_id,
                "store_id": store_id,
                "status": body.status or "ACTIVE",
                "access_token_preview": mask(body.access_token),
                "token_expires_at": expires_at.isoformat(),
                "source": "MANUAL",
            },
        )

    # ---------------------------------------------------------------------------
    # 2) 查询平台店铺状态  -> 从 store_tokens 读取
    #    GET /platform-shops/{platform}/{shop_id}
    # ---------------------------------------------------------------------------

    @router.get("/platform-shops/{platform}/{shop_id}", response_model=SimpleOut)
    async def get_platform_shop_status(
        platform: str,
        shop_id: str,
        session: AsyncSession = Depends(get_session),
    ) -> SimpleOut:
        """
        查询平台店铺当前状态（来自 store_tokens 表）。

        - 如果存在 OAuth / 手工 token → 返回 token 信息；
        - 如果不存在 → 返回 NOT_FOUND。
        """
        plat_upper = platform.upper()
        plat_lower = platform.lower()

        # 先找到对应的 store_id
        result = await session.execute(
            select(Store.id).where(
                Store.platform == plat_upper,
                Store.shop_id == shop_id,
            )
        )
        store_id_row = result.scalar_one_or_none()
        if not store_id_row:
            return SimpleOut(
                ok=False,
                data={
                    "platform": plat_upper,
                    "shop_id": shop_id,
                    "status": "STORE_NOT_FOUND",
                },
            )

        store_id = int(store_id_row)

        # 再查对应的 store_tokens
        result2 = await session.execute(
            select(StoreToken).where(
                StoreToken.store_id == store_id,
                StoreToken.platform == plat_lower,
            )
        )
        token_row = result2.scalar_one_or_none()

        if not token_row:
            return SimpleOut(
                ok=False,
                data={
                    "platform": plat_upper,
                    "shop_id": shop_id,
                    "store_id": store_id,
                    "status": "NOT_FOUND",
                },
            )

        return SimpleOut(
            ok=True,
            data={
                "platform": plat_upper,
                "shop_id": shop_id,
                "store_id": store_id,
                "status": "ACTIVE",
                "mall_id": token_row.mall_id,
                "access_token_preview": mask(token_row.access_token or ""),
                "token_expires_at": token_row.expires_at.isoformat(),
                "created_at": token_row.created_at.isoformat(),
                "updated_at": token_row.updated_at.isoformat(),
                "source": ("MANUAL" if token_row.refresh_token == "MANUAL" else "OAUTH"),
            },
        )
