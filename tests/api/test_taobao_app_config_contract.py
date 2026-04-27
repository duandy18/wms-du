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


async def _clear_taobao_app_configs(session) -> None:
    await session.execute(text("DELETE FROM taobao_app_configs"))
    await session.commit()


@pytest.mark.asyncio
async def test_get_current_taobao_app_config_returns_empty_shell_when_missing(client, session, monkeypatch):
    await _clear_taobao_app_configs(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        resp = await client.get("/oms/taobao/app-config/current")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["id"] is None
        assert data["app_key"] == ""
        assert data["app_secret_present"] is False
        assert data["app_secret_masked"] == ""
        assert data["callback_url"] == ""
        assert data["api_base_url"] == "https://eco.taobao.com/router/rest"
        assert data["sign_method"] == "md5"
        assert data["is_enabled"] is False
        assert data["created_at"] is None
        assert data["updated_at"] is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_put_current_taobao_app_config_create_then_get_masked(client, session, monkeypatch):
    await _clear_taobao_app_configs(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        payload = {
            "app_key": "tb-app-key-001",
            "app_secret": "tb-secret-xyz-001",
            "callback_url": "http://127.0.0.1:8000/oms/taobao/oauth/callback",
            "api_base_url": "https://eco.taobao.com/router/rest",
            "sign_method": "md5",
        }

        put_resp = await client.put("/oms/taobao/app-config/current", json=payload)
        assert put_resp.status_code == 200, put_resp.text

        put_body = put_resp.json()
        assert put_body["ok"] is True
        put_data = put_body["data"]

        assert isinstance(put_data["id"], int) and put_data["id"] > 0
        assert put_data["app_key"] == payload["app_key"]
        assert put_data["app_secret_present"] is True
        assert isinstance(put_data["app_secret_masked"], str) and put_data["app_secret_masked"]
        assert put_data["app_secret_masked"] != payload["app_secret"]
        assert put_data["callback_url"] == payload["callback_url"]
        assert put_data["api_base_url"] == payload["api_base_url"]
        assert put_data["sign_method"] == payload["sign_method"]
        assert put_data["is_enabled"] is True
        assert put_data["created_at"] is not None
        assert put_data["updated_at"] is not None

        get_resp = await client.get("/oms/taobao/app-config/current")
        assert get_resp.status_code == 200, get_resp.text

        get_body = get_resp.json()
        assert get_body["ok"] is True
        get_data = get_body["data"]

        assert get_data["id"] == put_data["id"]
        assert get_data["app_key"] == payload["app_key"]
        assert get_data["app_secret_present"] is True
        assert get_data["app_secret_masked"] != payload["app_secret"]
        assert get_data["callback_url"] == payload["callback_url"]
        assert get_data["api_base_url"] == payload["api_base_url"]
        assert get_data["sign_method"] == payload["sign_method"]
        assert get_data["is_enabled"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_put_current_taobao_app_config_blank_secret_keeps_existing_secret(client, session, monkeypatch):
    await _clear_taobao_app_configs(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        create_payload = {
            "app_key": "tb-app-key-001",
            "app_secret": "tb-secret-xyz-001",
            "callback_url": "http://127.0.0.1:8000/oms/taobao/oauth/callback",
            "api_base_url": "https://eco.taobao.com/router/rest",
            "sign_method": "md5",
        }
        r1 = await client.put("/oms/taobao/app-config/current", json=create_payload)
        assert r1.status_code == 200, r1.text
        secret_mask_before = r1.json()["data"]["app_secret_masked"]

        update_payload = {
            "app_key": "tb-app-key-002",
            "app_secret": "",
            "callback_url": "http://127.0.0.1:8000/oms/taobao/oauth/callback?updated=1",
            "api_base_url": "https://eco.taobao.com/router/rest",
            "sign_method": "md5",
        }
        r2 = await client.put("/oms/taobao/app-config/current", json=update_payload)
        assert r2.status_code == 200, r2.text

        body = r2.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["app_key"] == "tb-app-key-002"
        assert data["callback_url"] == "http://127.0.0.1:8000/oms/taobao/oauth/callback?updated=1"
        assert data["app_secret_present"] is True
        assert data["app_secret_masked"] == secret_mask_before
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_put_current_taobao_app_config_requires_secret_on_first_create(client, session, monkeypatch):
    await _clear_taobao_app_configs(session)

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        payload = {
            "app_key": "tb-app-key-001",
            "app_secret": "",
            "callback_url": "http://127.0.0.1:8000/oms/taobao/oauth/callback",
            "api_base_url": "https://eco.taobao.com/router/rest",
            "sign_method": "md5",
        }

        resp = await client.put("/oms/taobao/app-config/current", json=payload)
        assert resp.status_code == 400, resp.text
        assert "app_secret is required when creating taobao app config" in resp.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
