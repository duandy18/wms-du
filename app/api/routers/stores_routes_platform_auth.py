# app/api/routers/stores_routes_platform_auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db
from app.api.routers.stores_schemas import StorePlatformAuthOut


def register(router: APIRouter) -> None:
    @router.get(
        "/stores/{store_id}/platform-auth",
        response_model=StorePlatformAuthOut,
    )
    async def get_store_platform_auth(
        store_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        店铺平台授权状态视图：

        data:
          - store_id
          - platform
          - shop_id
          - auth_source: "NONE" / "MANUAL" / "OAUTH"
          - expires_at
          - mall_id
        """
        from app.api.routers import stores as stores_router

        stores_router._check_perm(db, current_user, ["config.store.read"])

        # 1) 查 store 平台与 shop_id
        sql_store = text(
            """
            SELECT platform, shop_id
              FROM stores
             WHERE id = :sid
             LIMIT 1
            """
        )
        row = (await session.execute(sql_store, {"sid": store_id})).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="store not found")

        platform = (row["platform"] or "").upper()
        shop_id = row["shop_id"]

        # 2) 查 store_tokens（按 store_id + platform 小写）
        sql_token = text(
            """
            SELECT mall_id, expires_at, refresh_token
              FROM store_tokens
             WHERE store_id = :sid
               AND platform = :plat
             ORDER BY id DESC
             LIMIT 1
            """
        )
        row_token = (
            (
                await session.execute(
                    sql_token,
                    {"sid": store_id, "plat": platform.lower()},
                )
            )
            .mappings()
            .first()
        )

        if not row_token:
            return StorePlatformAuthOut(
                ok=True,
                data={
                    "store_id": store_id,
                    "platform": platform,
                    "shop_id": shop_id,
                    "auth_source": "NONE",
                    "expires_at": None,
                    "mall_id": None,
                },
            )

        refresh_token = row_token["refresh_token"] or ""
        auth_source = "MANUAL" if refresh_token == "MANUAL" else "OAUTH"

        return StorePlatformAuthOut(
            ok=True,
            data={
                "store_id": store_id,
                "platform": platform,
                "shop_id": shop_id,
                "auth_source": auth_source,
                "expires_at": row_token["expires_at"].isoformat()
                if row_token["expires_at"]
                else None,
                "mall_id": row_token["mall_id"],
            },
        )
