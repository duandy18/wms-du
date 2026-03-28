# app/oms/platforms/taobao/service_auth.py
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from .repository import (
    ConnectionUpsertInput,
    CredentialUpsertInput,
    upsert_connection_by_store_platform,
    upsert_credential_by_store_platform,
)
from .settings import TaobaoTopConfig


TAOBAO_PLATFORM = "taobao"


class TaobaoAuthServiceError(Exception):
    """OMS 淘宝授权服务异常。"""


@dataclass(frozen=True)
class TaobaoAuthorizeUrlResult:
    authorize_url: str
    state: str


@dataclass(frozen=True)
class TaobaoAuthCallbackResult:
    store_id: int
    platform: str
    access_token: str
    refresh_token: Optional[str]
    expires_at: datetime
    granted_identity_type: Optional[str]
    granted_identity_value: Optional[str]
    granted_identity_display: Optional[str]
    raw_payload: Dict[str, Any]


class TaobaoAuthService:
    """
    OMS / 淘宝授权服务。

    当前职责：
    - 生成淘宝授权链接
    - 解析 state
    - 用 code 换授权材料
    - 写入 store_platform_credentials
    - 更新 store_platform_connections

    当前不负责：
    - router / HTML callback 页面
    - test-pull
    - 独立 identity 表（本期不建）
    """

    DEFAULT_AUTHORIZE_URL = "https://oauth.taobao.com/authorize"
    DEFAULT_TOKEN_URL = "https://oauth.taobao.com/token"

    def __init__(
        self,
        session: AsyncSession,
        *,
        config: TaobaoTopConfig,
        callback_url: str,
        authorize_url: Optional[str] = None,
        token_url: Optional[str] = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.session = session
        self.config = config
        self.callback_url = str(callback_url or "").strip()
        self.authorize_url = str(authorize_url or self.DEFAULT_AUTHORIZE_URL).strip()
        self.token_url = str(token_url or self.DEFAULT_TOKEN_URL).strip()
        self.timeout_seconds = timeout_seconds

        if not self.callback_url:
            raise TaobaoAuthServiceError("callback_url is required")
        if not self.authorize_url:
            raise TaobaoAuthServiceError("authorize_url is required")
        if not self.token_url:
            raise TaobaoAuthServiceError("token_url is required")

    def build_authorize_url(self, *, store_id: int) -> TaobaoAuthorizeUrlResult:
        if store_id <= 0:
            raise TaobaoAuthServiceError("store_id must be > 0")

        rand = secrets.token_urlsafe(24)
        state = f"{rand}.{TAOBAO_PLATFORM}.{store_id}"

        params = {
            "response_type": "code",
            "client_id": self.config.app_key,
            "redirect_uri": self.callback_url,
            "state": state,
            "view": "web",
        }
        authorize_url = f"{self.authorize_url}?{urlencode(params)}"
        return TaobaoAuthorizeUrlResult(authorize_url=authorize_url, state=state)

    async def handle_callback(
        self,
        *,
        code: str,
        state: str,
    ) -> TaobaoAuthCallbackResult:
        code = str(code or "").strip()
        state = str(state or "").strip()

        if not code:
            raise TaobaoAuthServiceError("code is required")
        if not state:
            raise TaobaoAuthServiceError("state is required")

        platform, store_id = self._parse_state(state)
        if platform != TAOBAO_PLATFORM:
            raise TaobaoAuthServiceError(
                f"state platform mismatch: expected={TAOBAO_PLATFORM}, actual={platform}"
            )

        token_payload = await self._exchange_code_for_token(code=code)
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(token_payload["expires_in"])
        )

        await upsert_credential_by_store_platform(
            self.session,
            data=CredentialUpsertInput(
                store_id=store_id,
                platform=TAOBAO_PLATFORM,
                credential_type="oauth",
                access_token=token_payload["access_token"],
                refresh_token=token_payload.get("refresh_token"),
                expires_at=expires_at,
                scope=token_payload.get("scope"),
                raw_payload_json=token_payload["raw_payload"],
                granted_identity_type=token_payload.get("granted_identity_type"),
                granted_identity_value=token_payload.get("granted_identity_value"),
                granted_identity_display=token_payload.get("granted_identity_display"),
            ),
        )

        await upsert_connection_by_store_platform(
            self.session,
            data=ConnectionUpsertInput(
                store_id=store_id,
                platform=TAOBAO_PLATFORM,
                auth_source="oauth",
                connection_status="connected",
                credential_status="valid",
                reauth_required=False,
                pull_ready=False,
                status="auth_pending",
                status_reason=None,
                last_authorized_at=datetime.now(timezone.utc),
            ),
        )

        await self.session.commit()

        return TaobaoAuthCallbackResult(
            store_id=store_id,
            platform=TAOBAO_PLATFORM,
            access_token=token_payload["access_token"],
            refresh_token=token_payload.get("refresh_token"),
            expires_at=expires_at,
            granted_identity_type=token_payload.get("granted_identity_type"),
            granted_identity_value=token_payload.get("granted_identity_value"),
            granted_identity_display=token_payload.get("granted_identity_display"),
            raw_payload=token_payload["raw_payload"],
        )

    def _parse_state(self, state: str) -> Tuple[str, int]:
        try:
            _, platform_str, store_id_str = state.split(".", 2)
        except ValueError as exc:
            raise TaobaoAuthServiceError(f"invalid state format: {state!r}") from exc

        platform = str(platform_str or "").strip().lower()
        if not platform:
            raise TaobaoAuthServiceError("state platform is empty")

        try:
            store_id = int(store_id_str)
        except ValueError as exc:
            raise TaobaoAuthServiceError(f"invalid store_id in state: {state!r}") from exc

        if store_id <= 0:
            raise TaobaoAuthServiceError(f"invalid store_id in state: {state!r}")

        return platform, store_id

    async def _exchange_code_for_token(self, *, code: str) -> Dict[str, Any]:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.config.app_key,
            "client_secret": self.config.app_secret,
            "redirect_uri": self.callback_url,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.token_url, data=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TaobaoAuthServiceError(
                f"taobao oauth token http status error: {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise TaobaoAuthServiceError(
                f"taobao oauth token request error: {exc}"
            ) from exc

        try:
            data = response.json()
        except Exception as exc:
            raise TaobaoAuthServiceError(
                "taobao oauth token returned invalid json"
            ) from exc

        if not isinstance(data, dict):
            raise TaobaoAuthServiceError(
                "taobao oauth token returned non-object json"
            )

        if "error" in data:
            raise TaobaoAuthServiceError(
                f"taobao oauth token exchange failed: {data}"
            )

        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise TaobaoAuthServiceError(
                f"taobao oauth token missing access_token: {data}"
            )

        expires_in_raw = data.get("expires_in")
        try:
            expires_in = int(expires_in_raw)
        except Exception as exc:
            raise TaobaoAuthServiceError(
                f"taobao oauth token missing/invalid expires_in: {data}"
            ) from exc

        refresh_token_raw = data.get("refresh_token")
        refresh_token = (
            str(refresh_token_raw).strip() if refresh_token_raw is not None else None
        )
        scope_raw = data.get("scope")
        scope = str(scope_raw).strip() if scope_raw is not None else None

        granted_identity_value = self._first_non_empty_str(
            data,
            "taobao_user_id",
            "user_id",
        )
        granted_identity_display = self._first_non_empty_str(
            data,
            "taobao_user_nick",
            "nick",
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": expires_in,
            "scope": scope,
            "granted_identity_type": (
                "taobao_user_id" if granted_identity_value else None
            ),
            "granted_identity_value": granted_identity_value,
            "granted_identity_display": granted_identity_display,
            "raw_payload": data,
        }

    @staticmethod
    def _first_non_empty_str(data: Dict[str, Any], *keys: str) -> Optional[str]:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None
