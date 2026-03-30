# app/oms/platforms/jd/service_auth.py
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from .repository import (
    ConnectionUpsertInput,
    CredentialUpsertInput,
    upsert_connection_by_store_platform,
    upsert_credential_by_store_platform,
)
from .settings import JdJosConfig


JD_PLATFORM = "jd"


class JdAuthServiceError(Exception):
    """OMS 京东 OAuth 服务异常。"""


@dataclass(frozen=True)
class JdAuthorizeUrlResult:
    platform: str
    store_id: int
    authorize_url: str
    state: str


@dataclass(frozen=True)
class JdAuthCallbackResult:
    platform: str
    store_id: int
    uid: Optional[str]
    uid_display: Optional[str]
    access_token: str
    refresh_token: Optional[str]
    expires_at: datetime
    raw_payload: Dict[str, Any]


class JdAuthService:
    """
    OMS / 京东授权服务。

    当前职责：
    - 生成京东授权链接
    - 解析 / 校验 state
    - 用 code 换 token
    - 写入 store_platform_credentials
    - 更新 store_platform_connections

    当前不负责：
    - router / HTML callback 页面
    - test-pull
    - 订单拉取
    - 事实表入库
    """

    DEFAULT_AUTHORIZE_URL = "https://open-oauth.jd.com/oauth2/to_login"
    DEFAULT_TOKEN_URL = "https://open-oauth.jd.com/oauth2/access_token"

    def __init__(
        self,
        session,
        *,
        config: JdJosConfig,
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
            raise JdAuthServiceError("callback_url is required")
        if not self.authorize_url:
            raise JdAuthServiceError("authorize_url is required")
        if not self.token_url:
            raise JdAuthServiceError("token_url is required")

    def build_authorize_url(self, *, store_id: int) -> JdAuthorizeUrlResult:
        if store_id <= 0:
            raise JdAuthServiceError("store_id must be positive")

        state = self._build_state(store_id=store_id)

        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.callback_url,
            "state": state,
        }

        from urllib.parse import urlencode

        authorize_url = f"{self.authorize_url}?{urlencode(params)}"

        return JdAuthorizeUrlResult(
            platform=JD_PLATFORM,
            store_id=store_id,
            authorize_url=authorize_url,
            state=state,
        )

    async def handle_callback(
        self,
        *,
        code: str,
        state: str,
    ) -> JdAuthCallbackResult:
        code_text = str(code or "").strip()
        state_text = str(state or "").strip()

        if not code_text:
            raise JdAuthServiceError("code is required")
        if not state_text:
            raise JdAuthServiceError("state is required")

        platform, store_id = self._parse_state(state_text)
        if platform != JD_PLATFORM:
            raise JdAuthServiceError(f"unexpected platform in state: {platform!r}")

        token_payload = await self._exchange_code_for_token(code=code_text)

        access_token = str(token_payload.get("access_token") or "").strip()
        if not access_token:
            raise JdAuthServiceError(f"jd oauth token missing access_token: {token_payload}")

        refresh_token_raw = token_payload.get("refresh_token")
        refresh_token = str(refresh_token_raw or "").strip() or None

        expires_in_raw = token_payload.get("expires_in")
        expires_at = self._parse_expires_at(expires_in=expires_in_raw)

        uid = self._first_non_empty_str(token_payload, "uid", "user_id")
        uid_display = self._first_non_empty_str(
            token_payload,
            "user_nick",
            "username",
            "nick",
        )

        now = datetime.now(timezone.utc)

        await upsert_credential_by_store_platform(
            self.session,
            data=CredentialUpsertInput(
                store_id=store_id,
                platform=JD_PLATFORM,
                credential_type="oauth",
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scope=self._first_non_empty_str(token_payload, "scope"),
                raw_payload_json=token_payload,
                granted_identity_type="jd_uid" if uid else None,
                granted_identity_value=uid,
                granted_identity_display=uid_display,
            ),
        )

        await upsert_connection_by_store_platform(
            self.session,
            data=ConnectionUpsertInput(
                store_id=store_id,
                platform=JD_PLATFORM,
                auth_source="oauth",
                connection_status="connected",
                credential_status="valid",
                reauth_required=False,
                pull_ready=False,
                status="auth_pending",
                status_reason=None,
                last_authorized_at=now,
            ),
        )

        await self.session.commit()

        return JdAuthCallbackResult(
            platform=JD_PLATFORM,
            store_id=store_id,
            uid=uid,
            uid_display=uid_display,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            raw_payload=token_payload,
        )

    def _build_state(self, *, store_id: int) -> str:
        payload = {
            "platform": JD_PLATFORM,
            "store_id": store_id,
            "nonce": secrets.token_urlsafe(16),
            "ts": int(datetime.now(timezone.utc).timestamp()),
        }
        payload_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")

        signature = hmac.new(
            self.config.client_secret.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return f"{payload_b64}.{signature}"

    def _parse_state(self, state: str) -> Tuple[str, int]:
        try:
            payload_b64, signature = state.split(".", 1)
        except ValueError as exc:
            raise JdAuthServiceError("invalid oauth state format") from exc

        expected = hmac.new(
            self.config.client_secret.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            raise JdAuthServiceError("invalid oauth state signature")

        padding = "=" * (-len(payload_b64) % 4)
        try:
            raw = base64.urlsafe_b64decode((payload_b64 + padding).encode("utf-8"))
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise JdAuthServiceError("invalid oauth state payload") from exc

        if not isinstance(data, dict):
            raise JdAuthServiceError("invalid oauth state object")

        platform = str(data.get("platform") or "").strip().lower()
        store_id = int(data.get("store_id") or 0)
        ts = int(data.get("ts") or 0)

        if platform != JD_PLATFORM:
            raise JdAuthServiceError(f"invalid oauth state platform: {platform!r}")
        if store_id <= 0:
            raise JdAuthServiceError("invalid oauth state store_id")
        if ts <= 0:
            raise JdAuthServiceError("invalid oauth state ts")

        now_ts = int(datetime.now(timezone.utc).timestamp())
        if abs(now_ts - ts) > 1800:
            raise JdAuthServiceError("oauth state expired")

        return platform, store_id

    async def _exchange_code_for_token(self, *, code: str) -> Dict[str, Any]:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "redirect_uri": self.callback_url,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.token_url, data=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise JdAuthServiceError(
                f"jd oauth token http status error: {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise JdAuthServiceError(
                f"jd oauth token request error: {exc}"
            ) from exc

        try:
            data = response.json()
        except Exception as exc:
            raise JdAuthServiceError("jd oauth token returned invalid json") from exc

        if not isinstance(data, dict):
            raise JdAuthServiceError("jd oauth token returned non-object json")

        if "error" in data:
            raise JdAuthServiceError(f"jd oauth token exchange failed: {data}")

        return data

    def _parse_expires_at(self, *, expires_in: object) -> datetime:
        expires_in_text = str(expires_in or "").strip()
        if expires_in_text.isdigit():
            return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in_text))

        raise JdAuthServiceError(
            f"jd oauth token missing/invalid expires_in: {expires_in!r}"
        )

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
