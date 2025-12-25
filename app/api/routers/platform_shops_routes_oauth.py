# app/api/routers/platform_shops_routes_oauth.py
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.platform_shops_helpers import OAUTH_REDIRECT_ALLOWLIST, audit
from app.api.routers.platform_shops_schemas import OAuthStartOut
from app.services.oauth_unified import PlatformOAuthError, UnifiedOAuthService
from app.services.store_service import StoreService


def register(router: APIRouter) -> None:
    # ---------------------------------------------------------------------------
    # 3) 统一 OAuth Start
    #    GET /oauth/{platform}/start
    # ---------------------------------------------------------------------------

    @router.get("/oauth/{platform}/start", response_model=OAuthStartOut)
    async def oauth_start(
        platform: str,
        shop_id: str,
        redirect_uri: str,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ) -> OAuthStartOut:
        plat_upper = platform.upper()

        # 允许的 redirect_uri 白名单检查（防钓鱼回调）
        if OAUTH_REDIRECT_ALLOWLIST and redirect_uri not in OAUTH_REDIRECT_ALLOWLIST:
            raise HTTPException(status_code=400, detail="redirect_uri not allowed")

        # 1) 确保内部 store 档案存在，并拿到 store_id
        store_id = await StoreService.ensure_store(
            session, platform=plat_upper, shop_id=shop_id, name=None
        )

        # 2) 统一 OAuth 服务生成授权 URL
        base_url = str(request.base_url).rstrip("/")
        svc = UnifiedOAuthService(db=session, base_url=base_url)

        try:
            authorize_url, state = await svc.build_auth_url(
                platform=plat_upper.lower(),  # "PDD" → "pdd"
                store_id=store_id,
            )
        except PlatformOAuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        # 3) 记录一次审计
        await audit(
            session,
            ref=f"AUTH:{plat_upper}:{shop_id}",
            meta={
                "event": "OAUTH_START",
                "redirect_uri": redirect_uri,
                "state": state,
                "store_id": store_id,
            },
        )

        return OAuthStartOut(
            ok=True,
            data={
                "authorize_url": authorize_url,
                "state": state,
            },
        )

    # ---------------------------------------------------------------------------
    # 4) 统一 OAuth Callback
    #    GET /oauth/{platform}/callback
    # ---------------------------------------------------------------------------

    @router.get("/oauth/{platform}/callback", response_class=HTMLResponse)
    async def oauth_callback(
        platform: str,
        code: str,
        state: str,
        request: Request,
        session: AsyncSession = Depends(get_session),
    ) -> HTMLResponse:
        plat_upper = platform.upper()
        base_url = str(request.base_url).rstrip("/")

        svc = UnifiedOAuthService(db=session, base_url=base_url)

        try:
            token_row, store_id = await svc.handle_callback(
                platform=plat_upper.lower(),  # "PDD" → "pdd"
                code=code,
                state=state,
            )
        except PlatformOAuthError as exc:
            # 回调场景，用 HTML 提示更友好
            return HTMLResponse(
                f"<h3>{plat_upper} 授权失败</h3><p>{exc}</p>",
                status_code=400,
            )

        await audit(
            session,
            ref=f"AUTH:{plat_upper}:{store_id}",
            meta={
                "event": "OAUTH_CALLBACK",
                "state": state,
                "store_id": store_id,
                "platform": plat_upper,
            },
        )

        html = f"""
        <html>
          <head><title>{plat_upper} 授权成功</title></head>
          <body>
            <h3>{plat_upper} 授权成功</h3>
            <p>店铺已绑定到内部 Store ID: {store_id}</p>
            <p>平台侧店铺 ID (mall_id / uid)：{token_row.mall_id or ""}</p>
            <p>Token 过期时间：{token_row.expires_at.isoformat()}</p>
            <p>现在可以关闭本窗口，回到 WMS-DU。</p>
          </body>
        </html>
        """
        return HTMLResponse(html)
