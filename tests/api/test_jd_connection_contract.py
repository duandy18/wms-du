from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.oms.platforms.models.store_platform_connection import StorePlatformConnection
from app.oms.platforms.models.store_platform_credential import StorePlatformCredential


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
  'jd',
  'store-{store_id}',
  'store-{store_id}',
  true
)
    ON CONFLICT (id) DO NOTHING
    """


async def _clear_jd_state(session) -> None:
    await session.execute(text("DELETE FROM store_platform_connections WHERE platform = 'jd'"))
    await session.execute(text("DELETE FROM store_platform_credentials WHERE platform = 'jd'"))
    await session.commit()


@pytest.mark.asyncio
async def test_get_store_jd_connection_returns_empty_shell_when_missing(client, session):
    await _clear_jd_state(session)
    await session.execute(text(_store_row_sql(601)))
    await session.commit()

    resp = await client.get("/oms/stores/601/jd/connection")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    data = body["data"]

    assert data["platform"] == "jd"
    assert data["store_id"] == 601
    assert data["credential_present"] is False
    assert data["credential_expires_at"] is None
    assert data["granted_identity_type"] is None
    assert data["granted_identity_value"] is None
    assert data["granted_identity_display"] is None
    assert data["auth_source"] == "none"
    assert data["connection_status"] == "not_connected"
    assert data["credential_status"] == "missing"
    assert data["reauth_required"] is False
    assert data["pull_ready"] is False
    assert data["status"] == "not_connected"
    assert data["status_reason"] is None
    assert data["last_authorized_at"] is None
    assert data["last_pull_checked_at"] is None
    assert data["last_error_at"] is None


@pytest.mark.asyncio
async def test_get_store_jd_connection_returns_connection_and_credential(client, session):
    now = datetime.now(timezone.utc)

    await _clear_jd_state(session)
    await session.execute(text(_store_row_sql(602)))

    session.add(
        StorePlatformCredential(
            store_id=602,
            platform="jd",
            credential_type="oauth",
            access_token="access-token-602",
            refresh_token="refresh-token-602",
            expires_at=now + timedelta(days=1),
            scope="jingdong.pop.order.search,jingdong.pop.order.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="jd_uid",
            granted_identity_value="uid-602",
            granted_identity_display="store-602",
        )
    )
    session.add(
        StorePlatformConnection(
            store_id=602,
            platform="jd",
            auth_source="oauth",
            connection_status="connected",
            credential_status="valid",
            reauth_required=False,
            pull_ready=True,
            status="ready",
            status_reason="real_pull_ok",
            last_authorized_at=now,
            last_pull_checked_at=now,
        )
    )
    await session.commit()

    resp = await client.get("/oms/stores/602/jd/connection")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    data = body["data"]

    assert data["platform"] == "jd"
    assert data["store_id"] == 602
    assert data["credential_present"] is True
    assert data["credential_expires_at"] is not None
    assert data["granted_identity_type"] == "jd_uid"
    assert data["granted_identity_value"] == "uid-602"
    assert data["granted_identity_display"] == "store-602"
    assert data["auth_source"] == "oauth"
    assert data["connection_status"] == "connected"
    assert data["credential_status"] == "valid"
    assert data["reauth_required"] is False
    assert data["pull_ready"] is True
    assert data["status"] == "ready"
    assert data["status_reason"] == "real_pull_ok"
    assert data["last_authorized_at"] is not None
    assert data["last_pull_checked_at"] is not None
