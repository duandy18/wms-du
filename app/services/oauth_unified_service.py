# app/services/oauth_unified_service.py
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Tuple
from urllib.parse import urlencode

import httpx
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store_token import StoreToken
from app.services.oauth_unified_types import (
    PLATFORM_CONFIGS,
    Platform,
    PlatformOAuthConfig,
    PlatformOAuthError,
    load_credentials,
)


class UnifiedOAuthService:
    """
    多平台 OAuth 统一服务：
    - build_auth_url(platform, store_id) -> (authorize_url, state)
    - handle_callback(platform, code, state) -> (StoreToken, store_id)
    """

    def __init__(self, db: AsyncSession, base_url: str):
        self.db = db
        self.base_url = base_url.rstrip("/")

    async def build_auth_url(self, platform: Platform, store_id: int) -> Tuple[str, str]:
        cfg = self._get_config(platform)
        client_id, _ = load_credentials(cfg)

        rand = secrets.token_urlsafe(16)
        state = f"{rand}.{platform}.{store_id}"
        redirect_uri = f"{self.base_url}{cfg.redirect_path}"

        if platform == "pdd":
            params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        elif platform == "tb":
            params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "view": "web",
            }
        elif platform == "jd":
            params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        else:
            raise PlatformOAuthError(f"未知平台: {platform}")

        authorize_url = f"{cfg.authorize_url}?{urlencode(params)}"
        return authorize_url, state

    async def handle_callback(
        self,
        platform: Platform,
        code: str,
        state: str,
    ) -> Tuple[StoreToken, int]:
        cfg = self._get_config(platform)
        client_id, client_secret = load_credentials(cfg)

        parsed_platform, store_id = self._parse_state(state)
        if parsed_platform != platform:
            raise PlatformOAuthError(f"state 中的平台({parsed_platform})与路径({platform})不一致")

        if platform == "pdd":
            token_data = await self._exchange_code_for_token_pdd(
                cfg, client_id, client_secret, code
            )
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            mall_id = str(token_data.get("owner_id") or "")
        elif platform == "tb":
            token_data = await self._exchange_code_for_token_tb(cfg, client_id, client_secret, code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            mall_id = str(token_data.get("taobao_user_id") or "")
        elif platform == "jd":
            token_data = await self._exchange_code_for_token_jd(cfg, client_id, client_secret, code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            mall_id = str(token_data.get("uid") or "")
        else:
            raise PlatformOAuthError(f"未知平台: {platform}")

        if not (access_token and refresh_token and expires_in):
            raise PlatformOAuthError(f"{platform} 返回 token 数据不完整: {token_data!r}")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

        stmt = sa.select(StoreToken).where(
            StoreToken.store_id == store_id,
            StoreToken.platform == platform,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.access_token = access_token
            existing.refresh_token = refresh_token
            existing.expires_at = expires_at
            existing.mall_id = mall_id or existing.mall_id
            token_row = existing
        else:
            token_row = StoreToken(
                store_id=store_id,
                platform=platform,
                mall_id=mall_id or None,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
            )
            self.db.add(token_row)

        await self.db.commit()
        await self.db.refresh(token_row)
        return token_row, store_id

    # ------------ 内部辅助 ------------

    def _get_config(self, platform: Platform) -> PlatformOAuthConfig:
        try:
            return PLATFORM_CONFIGS[platform]
        except KeyError:
            raise PlatformOAuthError(f"未配置的平台: {platform}")

    def _parse_state(self, state: str) -> Tuple[Platform, int]:
        try:
            _, platform_str, store_id_str = state.split(".", 2)
            platform_norm = platform_str  # state 里就是 "pdd/tb/jd"
            if platform_norm not in PLATFORM_CONFIGS:
                raise PlatformOAuthError(f"state 中平台不合法: {platform_norm!r}")
            return platform_norm, int(store_id_str)  # type: ignore[return-value]
        except PlatformOAuthError:
            raise
        except Exception as exc:
            raise PlatformOAuthError(f"state 解析失败: {state!r}") from exc

    # ------------ 各平台 token 换取 ------------

    async def _exchange_code_for_token_pdd(
        self,
        cfg: PlatformOAuthConfig,
        client_id: str,
        client_secret: str,
        code: str,
    ) -> dict:
        """
        PDD: type = pdd.pop.auth.token.create 走统一网关。
        这里省略签名 sign 细节，需要按官方文档实现。
        """
        payload = {
            "type": "pdd.pop.auth.token.create",
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "data_type": "JSON",
            "timestamp": int(datetime.now().timestamp()),
        }

        # TODO: 按 PDD 文档实现签名逻辑 calc_sign(payload, client_secret)
        # payload["sign"] = calc_sign(payload, client_secret)

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(cfg.token_url, data=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error_response" in data:
            raise PlatformOAuthError(f"PDD 授权失败: {data['error_response']}")

        token_data = data.get("pop_auth_token_create_response") or data
        return token_data

    async def _exchange_code_for_token_tb(
        self,
        cfg: PlatformOAuthConfig,
        client_id: str,
        client_secret: str,
        code: str,
    ) -> dict:
        """
        淘宝: 标准 OAuth2 token 接口，需按官方文档补齐参数与签名。
        """
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": f"{self.base_url}{cfg.redirect_path}",
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(cfg.token_url, data=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise PlatformOAuthError(f"TB 授权失败: {data}")
        return data

    async def _exchange_code_for_token_jd(
        self,
        cfg: PlatformOAuthConfig,
        client_id: str,
        client_secret: str,
        code: str,
    ) -> dict:
        """
        京东: OAuth2 token，参数名和返回结构需按官方文档对齐。
        """
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": f"{self.base_url}{cfg.redirect_path}",
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(cfg.token_url, data=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise PlatformOAuthError(f"JD 授权失败: {data}")
        return data
