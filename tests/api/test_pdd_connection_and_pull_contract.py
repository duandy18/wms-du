from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.user.deps.auth import get_current_user
from app.main import app
from app.platform_order_ingestion.models.pdd_app_config import PddAppConfig
from app.platform_order_ingestion.models.store_platform_connection import StorePlatformConnection
from app.platform_order_ingestion.models.store_platform_credential import StorePlatformCredential


class _TestUser:
    id: int = 999
    username: str = "test-user"
    is_active: bool = True
    permissions = ["page.platform_order_ingestion.read", "page.platform_order_ingestion.write"]


pytestmark = pytest.mark.asyncio


def _store_row_sql(store_id: int) -> str:
    return f"""
    INSERT INTO stores (
  id,
  platform,
  store_code,
  store_name,
  active
)
VALUES (
  {store_id},
  'pdd',
  'store-{store_id}',
  'store-{store_id}',
  true
)
    ON CONFLICT (id) DO NOTHING
    """


async def _clear_pdd_state(session) -> None:
    await session.execute(text("DELETE FROM store_platform_connections WHERE platform = 'pdd'"))
    await session.execute(text("DELETE FROM store_platform_credentials WHERE platform = 'pdd'"))
    await session.execute(text("DELETE FROM pdd_app_configs"))
    await session.commit()


@pytest.mark.asyncio
async def test_get_store_pdd_connection_returns_empty_shell_when_missing(client, session):
    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(401)))
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        resp = await client.get("/oms/stores/401/pdd/connection")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["platform"] == "pdd"
        assert data["store_id"] == 401
        assert data["auth_source"] == "none"
        assert data["connection_status"] == "not_connected"
        assert data["credential_status"] == "missing"
        assert data["reauth_required"] is False
        assert data["pull_ready"] is False
        assert data["status"] == "not_connected"
        assert data["status_reason"] == "authorization_missing"
        assert data["credential"] is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_store_pdd_connection_returns_connection_and_credential(client, session):
    now = datetime.now(timezone.utc)

    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(402)))

    session.add(
        StorePlatformCredential(
            store_id=402,
            platform="pdd",
            credential_type="oauth",
            access_token="access-token-402",
            refresh_token="refresh-token-402",
            expires_at=now + timedelta(days=1),
            scope="pdd.order.list.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="pdd_owner_id",
            granted_identity_value="owner-402",
            granted_identity_display="store-402",
        )
    )
    session.add(
        StorePlatformConnection(
            store_id=402,
            platform="pdd",
            auth_source="oauth",
            connection_status="connected",
            credential_status="valid",
            reauth_required=False,
            pull_ready=False,
            status="ready",
            status_reason="real_pull_not_implemented",
            last_authorized_at=now,
            last_pull_checked_at=now,
        )
    )
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        resp = await client.get("/oms/stores/402/pdd/connection")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["platform"] == "pdd"
        assert data["store_id"] == 402
        assert data["auth_source"] == "oauth"
        assert data["connection_status"] == "connected"
        assert data["credential_status"] == "valid"
        assert data["reauth_required"] is False
        assert data["pull_ready"] is False
        assert data["status"] == "ready"
        assert data["status_reason"] == "real_pull_not_implemented"
        assert data["credential"]["credential_type"] == "oauth"
        assert data["credential"]["access_token_present"] is True
        assert data["credential"]["refresh_token_present"] is True
        assert data["credential"]["granted_identity_type"] == "pdd_owner_id"
        assert data["credential"]["granted_identity_value"] == "owner-402"
        assert data["credential"]["granted_identity_display"] == "store-402"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_post_store_pdd_test_pull_returns_platform_app_not_ready(client, session):
    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(403)))
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        resp = await client.post("/oms/stores/403/pdd/test-pull")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["platform"] == "pdd"
        assert data["store_id"] == 403
        assert data["status"] == "not_ready"
        assert data["status_reason"] == "platform_app_not_ready"
        assert data["connection_status"] == "not_connected"
        assert data["credential_status"] == "missing"
        assert data["reauth_required"] is False
        assert data["pull_ready"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_post_store_pdd_test_pull_returns_credential_missing(client, session):
    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(404)))
    session.add(
        PddAppConfig(
            client_id="pdd-client-id-404",
            client_secret="pdd-client-secret-404",
            redirect_uri="http://127.0.0.1:8000/oms/pdd/oauth/callback",
            api_base_url="https://gw-api.pinduoduo.com/api/router",
            sign_method="md5",
            is_enabled=True,
        )
    )
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        resp = await client.post("/oms/stores/404/pdd/test-pull")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["platform"] == "pdd"
        assert data["store_id"] == 404
        assert data["status"] == "not_ready"
        assert data["status_reason"] == "credential_missing"
        assert data["connection_status"] == "not_connected"
        assert data["credential_status"] == "missing"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_post_store_pdd_test_pull_returns_real_pull_not_implemented(client, session):
    now = datetime.now(timezone.utc)

    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(405)))
    session.add(
        PddAppConfig(
            client_id="pdd-client-id-405",
            client_secret="pdd-client-secret-405",
            redirect_uri="http://127.0.0.1:8000/oms/pdd/oauth/callback",
            api_base_url="https://gw-api.pinduoduo.com/api/router",
            sign_method="md5",
            is_enabled=True,
        )
    )
    session.add(
        StorePlatformCredential(
            store_id=405,
            platform="pdd",
            credential_type="oauth",
            access_token="access-token-405",
            refresh_token="refresh-token-405",
            expires_at=now + timedelta(days=1),
            scope="pdd.order.list.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="pdd_owner_id",
            granted_identity_value="owner-405",
            granted_identity_display="store-405",
        )
    )
    await session.commit()

    app.dependency_overrides[get_current_user] = lambda: _TestUser()

    try:
        resp = await client.post("/oms/stores/405/pdd/test-pull")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["ok"] is True
        data = body["data"]

        assert data["platform"] == "pdd"
        assert data["store_id"] == 405
        assert data["status"] == "ready"
        assert data["status_reason"] == "real_pull_not_implemented"
        assert data["connection_status"] == "connected"
        assert data["credential_status"] == "valid"
        assert data["reauth_required"] is False
        assert data["pull_ready"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)
