from __future__ import annotations

import pytest
from sqlalchemy import text

from app.user.deps.auth import get_current_user
from app.main import app


class _TestUser:
    id: int = 999
    username: str = "test-user"
    is_active: bool = True
    permissions = ["page.platform_order_ingestion.read", "page.platform_order_ingestion.write"]


pytestmark = pytest.mark.asyncio


async def _clear_pdd_app_configs(session) -> None:
    await session.execute(text("DELETE FROM pdd_app_configs"))
    await session.commit()


@pytest.mark.asyncio
async def test_get_current_pdd_app_config_returns_empty_shell_when_missing(client, session, monkeypatch):
    await _clear_pdd_app_configs(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        resp = await client.get("/oms/pdd/app-config/current")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["id"] is None
        assert data["client_id"] == ""
        assert data["client_secret_present"] is False
        assert data["client_secret_masked"] == ""
        assert data["redirect_uri"] == ""
        assert data["api_base_url"] == "https://gw-api.pinduoduo.com/api/router"
        assert data["sign_method"] == "md5"
        assert data["is_enabled"] is False
        assert data["created_at"] is None
        assert data["updated_at"] is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_put_current_pdd_app_config_create_then_get_masked(client, session, monkeypatch):
    await _clear_pdd_app_configs(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        payload = {
            "client_id": "pdd-client-id-001",
            "client_secret": "pdd-client-secret-001",
            "redirect_uri": "http://127.0.0.1:8000/oms/pdd/oauth/callback",
            "api_base_url": "https://gw-api.pinduoduo.com/api/router",
            "sign_method": "md5",
        }

        put_resp = await client.put("/oms/pdd/app-config/current", json=payload)
        assert put_resp.status_code == 200, put_resp.text

        put_body = put_resp.json()
        assert put_body["ok"] is True
        put_data = put_body["data"]

        assert isinstance(put_data["id"], int) and put_data["id"] > 0
        assert put_data["client_id"] == payload["client_id"]
        assert put_data["client_secret_present"] is True
        assert isinstance(put_data["client_secret_masked"], str) and put_data["client_secret_masked"]
        assert put_data["client_secret_masked"] != payload["client_secret"]
        assert put_data["redirect_uri"] == payload["redirect_uri"]
        assert put_data["api_base_url"] == payload["api_base_url"]
        assert put_data["sign_method"] == payload["sign_method"]
        assert put_data["is_enabled"] is True
        assert put_data["created_at"] is not None
        assert put_data["updated_at"] is not None

        get_resp = await client.get("/oms/pdd/app-config/current")
        assert get_resp.status_code == 200, get_resp.text

        get_body = get_resp.json()
        assert get_body["ok"] is True
        get_data = get_body["data"]

        assert get_data["id"] == put_data["id"]
        assert get_data["client_id"] == payload["client_id"]
        assert get_data["client_secret_present"] is True
        assert get_data["client_secret_masked"] != payload["client_secret"]
        assert get_data["redirect_uri"] == payload["redirect_uri"]
        assert get_data["api_base_url"] == payload["api_base_url"]
        assert get_data["sign_method"] == payload["sign_method"]
        assert get_data["is_enabled"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_put_current_pdd_app_config_blank_secret_keeps_existing_secret(client, session, monkeypatch):
    await _clear_pdd_app_configs(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        create_payload = {
            "client_id": "pdd-client-id-001",
            "client_secret": "pdd-client-secret-001",
            "redirect_uri": "http://127.0.0.1:8000/oms/pdd/oauth/callback",
            "api_base_url": "https://gw-api.pinduoduo.com/api/router",
            "sign_method": "md5",
        }
        r1 = await client.put("/oms/pdd/app-config/current", json=create_payload)
        assert r1.status_code == 200, r1.text
        secret_mask_before = r1.json()["data"]["client_secret_masked"]

        update_payload = {
            "client_id": "pdd-client-id-002",
            "client_secret": "",
            "redirect_uri": "http://127.0.0.1:8000/oms/pdd/oauth/callback?updated=1",
            "api_base_url": "https://gw-api.pinduoduo.com/api/router",
            "sign_method": "md5",
        }
        r2 = await client.put("/oms/pdd/app-config/current", json=update_payload)
        assert r2.status_code == 200, r2.text

        body = r2.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["client_id"] == "pdd-client-id-002"
        assert data["redirect_uri"] == "http://127.0.0.1:8000/oms/pdd/oauth/callback?updated=1"
        assert data["client_secret_present"] is True
        assert data["client_secret_masked"] == secret_mask_before
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_put_current_pdd_app_config_requires_secret_on_first_create(client, session, monkeypatch):
    await _clear_pdd_app_configs(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        payload = {
            "client_id": "pdd-client-id-001",
            "client_secret": "",
            "redirect_uri": "http://127.0.0.1:8000/oms/pdd/oauth/callback",
            "api_base_url": "https://gw-api.pinduoduo.com/api/router",
            "sign_method": "md5",
        }

        resp = await client.put("/oms/pdd/app-config/current", json=payload)
        assert resp.status_code == 400, resp.text
        assert "client_secret is required when creating pdd app config" in resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
