from __future__ import annotations

import pytest
from sqlalchemy import text

from app.user.deps.auth import get_current_user
from app.main import app
from app.oms.platforms.pdd import router_auth as pdd_router_auth
from app.oms.platforms.pdd.repository import (
    PddAppConfigUpsertInput,
    upsert_current_pdd_app_config,
)
from app.oms.platforms.pdd.service_auth import PddAuthCallbackResult, PddAuthServiceError
from app.oms.services import stores_helpers


class _TestUser:
    id: int = 999
    username: str = "test-user"
    is_active: bool = True


pytestmark = pytest.mark.asyncio


async def _clear_pdd_state(session) -> None:
    await session.execute(text("DELETE FROM store_platform_connections WHERE platform = 'pdd'"))
    await session.execute(text("DELETE FROM store_platform_credentials WHERE platform = 'pdd'"))
    await session.execute(text("DELETE FROM pdd_app_configs"))
    await session.commit()


async def _seed_pdd_app_config(session) -> None:
    await upsert_current_pdd_app_config(
        session,
        data=PddAppConfigUpsertInput(
            client_id="pdd-client-id-001",
            client_secret="pdd-client-secret-001",
            redirect_uri="http://127.0.0.1:8000/oms/pdd/oauth/callback",
            api_base_url="https://gw-api.pinduoduo.com/api/router",
            sign_method="md5",
            is_enabled=True,
        ),
    )
    await session.commit()


@pytest.mark.asyncio
async def test_pdd_oauth_start_returns_authorize_url(client, session, monkeypatch):
    await _clear_pdd_state(session)
    await _seed_pdd_app_config(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()
    monkeypatch.setattr(stores_helpers, "check_perm", lambda db, current_user, required: None)

    try:
        resp = await client.get("/oms/pdd/oauth/start", params={"store_id": 101})
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["platform"] == "pdd"
        assert data["store_id"] == 101
        assert isinstance(data["state"], str) and data["state"]
        assert isinstance(data["authorize_url"], str) and data["authorize_url"]
        assert data["authorize_url"].startswith(
            "https://fuwu.pinduoduo.com/service-market/auth?"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_pdd_oauth_start_requires_enabled_app_config(client, session, monkeypatch):
    await _clear_pdd_state(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()
    monkeypatch.setattr(stores_helpers, "check_perm", lambda db, current_user, required: None)

    try:
        resp = await client.get("/oms/pdd/oauth/start", params={"store_id": 101})
        assert resp.status_code == 400, resp.text
        assert "enabled pdd app config not found" in resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_pdd_oauth_callback_success(client, session, monkeypatch):
    await _clear_pdd_state(session)
    await _seed_pdd_app_config(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    original_handle_callback = pdd_router_auth.PddAuthService.handle_callback

    async def _fake_handle_callback(self, *, session, code: str, state: str):
        from datetime import datetime, timezone

        assert code == "callback-code-001"
        assert isinstance(state, str) and state

        return PddAuthCallbackResult(
            platform="pdd",
            store_id=202,
            owner_id="owner-202",
            owner_name="store-202",
            access_token="access-token-202",
            refresh_token="refresh-token-202",
            expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(
        pdd_router_auth.PddAuthService,
        "handle_callback",
        _fake_handle_callback,
    )

    try:
        resp = await client.get(
            "/oms/pdd/oauth/callback",
            params={
                "code": "callback-code-001",
                "state": "test-state-001",
            },
        )
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["platform"] == "pdd"
        assert data["store_id"] == 202
        assert data["owner_id"] == "owner-202"
        assert data["owner_name"] == "store-202"
        assert data["access_token_present"] is True
        assert data["refresh_token_present"] is True
        assert data["expires_at"] == "2030-01-01T00:00:00+00:00"
    finally:
        monkeypatch.setattr(
            pdd_router_auth.PddAuthService,
            "handle_callback",
            original_handle_callback,
        )
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_pdd_oauth_callback_surfaces_service_validation_error(client, session, monkeypatch):
    await _clear_pdd_state(session)
    await _seed_pdd_app_config(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    original_handle_callback = pdd_router_auth.PddAuthService.handle_callback

    async def _fake_handle_callback(self, *, session, code: str, state: str):
        raise PddAuthServiceError("invalid oauth state signature")

    monkeypatch.setattr(
        pdd_router_auth.PddAuthService,
        "handle_callback",
        _fake_handle_callback,
    )

    try:
        resp = await client.get(
            "/oms/pdd/oauth/callback",
            params={
                "code": "callback-code-002",
                "state": "bad-state-001",
            },
        )
        assert resp.status_code == 400, resp.text
        assert "invalid oauth state signature" in resp.text
    finally:
        monkeypatch.setattr(
            pdd_router_auth.PddAuthService,
            "handle_callback",
            original_handle_callback,
        )
        app.dependency_overrides.pop(get_current_user, None)
