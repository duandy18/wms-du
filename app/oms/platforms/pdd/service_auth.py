# app/oms/platforms/pdd/service_auth.py
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

from .access_repository import (
    ConnectionUpsertInput,
    CredentialUpsertInput,
    upsert_connection_by_store_platform,
    upsert_credential_by_store_platform,
)
from .client import PddOpenClient, PddOpenClientError
from .settings import PddOpenConfig


PDD_PLATFORM = "pdd"


class PddAuthServiceError(Exception):
    """OMS 拼多多 OAuth 服务异常。"""


@dataclass(frozen=True)
class PddAuthorizeUrlResult:
    platform: str
    store_id: int
    authorize_url: str
    state: str


@dataclass(frozen=True)
class PddAuthCallbackResult:
    platform: str
    store_id: int
    owner_id: Optional[str]
    owner_name: Optional[str]
    access_token: str
    refresh_token: Optional[str]
    expires_at: datetime


class PddAuthService:
    DEFAULT_AUTHORIZE_URL = "https://fuwu.pinduoduo.com/service-market/auth"
    DEFAULT_TOKEN_TYPE = "pdd.pop.auth.token.create"

    def __init__(
        self,
        *,
        config: PddOpenConfig,
        redirect_uri: str,
    ) -> None:
        self.config = config
        self.redirect_uri = str(redirect_uri or "").strip()

        if not self.redirect_uri:
            raise PddAuthServiceError("redirect_uri is required")

    def build_authorize_url(self, *, store_id: int) -> PddAuthorizeUrlResult:
        if store_id <= 0:
            raise PddAuthServiceError("store_id must be positive")

        state = self._build_state(store_id=store_id)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.config.client_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
            }
        )
        authorize_url = f"{self.DEFAULT_AUTHORIZE_URL}?{query}"

        return PddAuthorizeUrlResult(
            platform=PDD_PLATFORM,
            store_id=store_id,
            authorize_url=authorize_url,
            state=state,
        )

    async def handle_callback(
        self,
        *,
        session,
        code: str,
        state: str,
    ) -> PddAuthCallbackResult:
        code_text = str(code or "").strip()
        state_text = str(state or "").strip()

        if not code_text:
            raise PddAuthServiceError("code is required")
        if not state_text:
            raise PddAuthServiceError("state is required")

        platform, store_id = self._parse_state(state_text)
        if platform != PDD_PLATFORM:
            raise PddAuthServiceError(f"unexpected platform in state: {platform!r}")

        data = await self._exchange_code_for_token(code=code_text)

        token_resp = data.get("pop_auth_token_create_response")
        if not isinstance(token_resp, dict):
            raise PddAuthServiceError(
                f"pdd oauth token exchange returned invalid response: {data}"
            )

        access_token = str(token_resp.get("access_token") or "").strip()
        if not access_token:
            raise PddAuthServiceError(
                f"pdd oauth token missing access_token: {token_resp}"
            )

        refresh_token_raw = token_resp.get("refresh_token")
        refresh_token = str(refresh_token_raw or "").strip() or None

        expires_at_raw = token_resp.get("expires_at")
        expires_in_raw = token_resp.get("expires_in")

        expires_at = self._parse_expires_at(
            expires_at=expires_at_raw,
            expires_in=expires_in_raw,
        )

        owner_id = self._first_non_empty_str(token_resp, "owner_id")
        owner_name = self._first_non_empty_str(token_resp, "owner_name")

        scope_value: Optional[str] = None
        scope_raw = token_resp.get("scope")
        if isinstance(scope_raw, list):
            scope_items = [str(item).strip() for item in scope_raw if str(item).strip()]
            scope_value = ",".join(scope_items) if scope_items else None
        elif isinstance(scope_raw, str):
            scope_value = scope_raw.strip() or None

        now = datetime.now(timezone.utc)

        await upsert_credential_by_store_platform(
            session,
            data=CredentialUpsertInput(
                store_id=store_id,
                platform=PDD_PLATFORM,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scope=scope_value,
                raw_payload_json=data,
                granted_identity_type="pdd_owner_id" if owner_id else None,
                granted_identity_value=owner_id,
                granted_identity_display=owner_name,
            ),
        )

        await upsert_connection_by_store_platform(
            session,
            data=ConnectionUpsertInput(
                store_id=store_id,
                platform=PDD_PLATFORM,
                auth_source="oauth",
                connection_status="connected",
                credential_status="valid",
                reauth_required=False,
                pull_ready=True,
                status="connected",
                status_reason="authorization_ok",
                last_authorized_at=now,
            ),
        )

        return PddAuthCallbackResult(
            platform=PDD_PLATFORM,
            store_id=store_id,
            owner_id=owner_id,
            owner_name=owner_name,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

    def _build_state(self, *, store_id: int) -> str:
        payload = {
            "platform": PDD_PLATFORM,
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
            raise PddAuthServiceError("invalid oauth state format") from exc

        expected = hmac.new(
            self.config.client_secret.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise PddAuthServiceError("invalid oauth state signature")

        padding = "=" * (-len(payload_b64) % 4)
        try:
            raw = base64.urlsafe_b64decode((payload_b64 + padding).encode("utf-8"))
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise PddAuthServiceError("invalid oauth state payload") from exc

        if not isinstance(data, dict):
            raise PddAuthServiceError("invalid oauth state object")

        platform = str(data.get("platform") or "").strip().lower()
        store_id = int(data.get("store_id") or 0)
        ts = int(data.get("ts") or 0)

        if platform != PDD_PLATFORM:
            raise PddAuthServiceError(f"invalid oauth state platform: {platform!r}")
        if store_id <= 0:
            raise PddAuthServiceError("invalid oauth state store_id")
        if ts <= 0:
            raise PddAuthServiceError("invalid oauth state ts")

        now_ts = int(datetime.now(timezone.utc).timestamp())
        if abs(now_ts - ts) > 1800:
            raise PddAuthServiceError("oauth state expired")

        return platform, store_id

    async def _exchange_code_for_token(self, *, code: str) -> Dict[str, Any]:
        client = PddOpenClient(config=self.config)
        try:
            return await client.post(
                api_type=self.DEFAULT_TOKEN_TYPE,
                business_params={
                    "code": code,
                },
            )
        except PddOpenClientError as exc:
            raise PddAuthServiceError(f"pdd oauth token exchange failed: {exc}") from exc

    def _parse_expires_at(
        self,
        *,
        expires_at: object,
        expires_in: object,
    ) -> datetime:
        expires_at_text = str(expires_at or "").strip()
        if expires_at_text.isdigit():
            return datetime.fromtimestamp(int(expires_at_text), tz=timezone.utc)

        expires_in_text = str(expires_in or "").strip()
        if expires_in_text.isdigit():
            return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in_text))

        raise PddAuthServiceError(
            f"pdd oauth token missing/invalid expires_at and expires_in: expires_at={expires_at!r}, expires_in={expires_in!r}"
        )

    def _first_non_empty_str(self, data: Dict[str, Any], *keys: str) -> Optional[str]:
        for key in keys:
            value = str(data.get(key) or "").strip()
            if value:
                return value
        return None
