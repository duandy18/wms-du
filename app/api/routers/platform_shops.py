# app/api/routers/platform_shops.py
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, constr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.store import Store
from app.models.store_token import StoreToken
from app.services.oauth_unified import PlatformOAuthError, UnifiedOAuthService
from app.services.store_service import StoreService

router = APIRouter()

# 允许的前端 redirect_uri 白名单（防钓鱼回调）
# 多个地址用逗号分隔，例如：
# WMS_OAUTH_REDIRECT_ALLOWLIST=http://127.0.0.1:5173,http://localhost:5173
_OAUTH_ALLOWLIST_ENV = os.getenv("WMS_OAUTH_REDIRECT_ALLOWLIST", "")
OAUTH_REDIRECT_ALLOWLIST = {u.strip() for u in _OAUTH_ALLOWLIST_ENV.split(",") if u.strip()}


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class PlatformShopCredentialsIn(BaseModel):
    """
    手工录入平台店铺凭据（例如：为了快速联调用，不走 OAuth 流程）。
    """

    platform: constr(strip_whitespace=True, min_length=1, max_length=16)
    shop_id: constr(strip_whitespace=True, min_length=1, max_length=64)

    # 这里用一个通用字段名，底层落到 store_tokens.access_token
    access_token: constr(strip_whitespace=True, min_length=1)

    # 可选：显式传入过期时间。不传的话，我们默认 2 小时后过期。
    token_expires_at: Optional[datetime] = None

    status: Optional[constr(strip_whitespace=True, max_length=32)] = "ACTIVE"

    store_name: Optional[str] = None  # 便于首次接入顺手补录店铺名称


class SimpleOut(BaseModel):
    ok: bool
    data: Optional[Dict[str, Any]] = None


class OAuthStartOut(BaseModel):
    ok: bool
    data: Dict[str, Any]


class OAuthCallbackOut(BaseModel):
    ok: bool
    data: Dict[str, Any]


# ---------------------------------------------------------------------------
# 内部小工具
# ---------------------------------------------------------------------------


async def _audit(session: AsyncSession, ref: str, meta: Dict[str, Any]) -> None:
    """
    轻量级审计记录。

    - 如果存在 audit_event 表且结构兼容，就插进去；
    - 如果失败（表不存在 / 结构不兼容），就直接吞掉，不影响主流程。
    """
    payload = {
        "ref": ref,
        "meta": meta,
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "platform_oauth",
    }
    try:
        await session.execute(
            text(
                """
                INSERT INTO audit_event (ref, source, payload, created_at)
                VALUES (:ref, :source, :payload, now())
                """
            ),
            {
                "ref": ref,
                "source": "platform_shops",
                "payload": json.dumps(payload, ensure_ascii=False),
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()


def _mask(token: str, keep: int = 4) -> str:
    """
    打印时对 token 做脱敏展示。
    """
    if not token:
        return ""
    if len(token) <= keep:
        return "*" * len(token)
    return token[:keep] + "..."


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

    await _audit(
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
            "access_token_preview": _mask(body.access_token),
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
            "access_token_preview": _mask(token_row.access_token or ""),
            "token_expires_at": token_row.expires_at.isoformat(),
            "created_at": token_row.created_at.isoformat(),
            "updated_at": token_row.updated_at.isoformat(),
            "source": ("MANUAL" if token_row.refresh_token == "MANUAL" else "OAUTH"),
        },
    )


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
    await _audit(
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

    await _audit(
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
