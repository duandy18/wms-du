from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.oms.platforms.models.pdd_app_config import PddAppConfig
from app.oms.platforms.models.store_platform_connection import StorePlatformConnection
from app.oms.platforms.models.store_platform_credential import StorePlatformCredential
from app.oms.platforms.pdd.service_pull import PddPullService


def _pdd_app_config(
    *,
    row_id: int = 1,
    client_id: str = "pdd-client-id-001",
    client_secret: str = "pdd-client-secret-001",
    redirect_uri: str = "http://127.0.0.1:8000/oms/pdd/oauth/callback",
    api_base_url: str = "https://gw-api.pinduoduo.com/api/router",
    sign_method: str = "md5",
    is_enabled: bool = True,
) -> PddAppConfig:
    now = datetime.now(timezone.utc)
    return PddAppConfig(
        id=row_id,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        api_base_url=api_base_url,
        sign_method=sign_method,
        is_enabled=is_enabled,
        created_at=now,
        updated_at=now,
    )


def _store_row_sql(store_id: int) -> str:
    return f"""
    INSERT INTO stores (
        id, platform, shop_id, store_code, name, active
    ) VALUES (
        {store_id},
        'pdd',
        'shop-{store_id}',
        'SC{store_id}',
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
async def test_check_pull_ready_returns_platform_app_not_ready_when_missing(session):
    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(301)))
    await session.commit()

    service = PddPullService()
    result = await service.check_pull_ready(session=session, store_id=301)
    await session.commit()

    assert result.platform == "pdd"
    assert result.store_id == 301
    assert result.status == "not_ready"
    assert result.status_reason == "platform_app_not_ready"
    assert result.connection_status == "not_connected"
    assert result.credential_status == "missing"
    assert result.reauth_required is False
    assert result.pull_ready is False


@pytest.mark.asyncio
async def test_check_pull_ready_returns_credential_missing_when_no_credential(session):
    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(302)))
    session.add(_pdd_app_config(row_id=1001))
    await session.commit()

    service = PddPullService()
    result = await service.check_pull_ready(session=session, store_id=302)
    await session.commit()

    assert result.platform == "pdd"
    assert result.store_id == 302
    assert result.status == "not_ready"
    assert result.status_reason == "credential_missing"
    assert result.connection_status == "not_connected"
    assert result.credential_status == "missing"
    assert result.reauth_required is False
    assert result.pull_ready is False


@pytest.mark.asyncio
async def test_check_pull_ready_returns_credential_expired_when_token_expired(session):
    now = datetime.now(timezone.utc)

    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(303)))
    session.add(_pdd_app_config(row_id=1002))
    session.add(
        StorePlatformCredential(
            store_id=303,
            platform="pdd",
            credential_type="oauth",
            access_token="expired-token",
            refresh_token="refresh-token",
            expires_at=now - timedelta(minutes=5),
            scope="pdd.order.list.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="pdd_owner_id",
            granted_identity_value="owner-303",
            granted_identity_display="shop-303",
        )
    )
    await session.commit()

    service = PddPullService()
    result = await service.check_pull_ready(session=session, store_id=303)
    await session.commit()

    assert result.platform == "pdd"
    assert result.store_id == 303
    assert result.status == "not_ready"
    assert result.status_reason == "credential_expired"
    assert result.connection_status == "connected"
    assert result.credential_status == "expired"
    assert result.reauth_required is True
    assert result.pull_ready is False


@pytest.mark.asyncio
async def test_check_pull_ready_returns_real_pull_not_implemented_when_credential_valid(session):
    now = datetime.now(timezone.utc)

    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(304)))
    session.add(_pdd_app_config(row_id=1003))
    session.add(
        StorePlatformCredential(
            store_id=304,
            platform="pdd",
            credential_type="oauth",
            access_token="valid-token",
            refresh_token="refresh-token",
            expires_at=now + timedelta(days=1),
            scope="pdd.order.list.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="pdd_owner_id",
            granted_identity_value="owner-304",
            granted_identity_display="shop-304",
        )
    )
    await session.commit()

    service = PddPullService()
    result = await service.check_pull_ready(session=session, store_id=304)
    await session.commit()

    assert result.platform == "pdd"
    assert result.store_id == 304
    assert result.status == "ready"
    assert result.status_reason == "real_pull_not_implemented"
    assert result.connection_status == "connected"
    assert result.credential_status == "valid"
    assert result.reauth_required is False
    assert result.pull_ready is False


@pytest.mark.asyncio
async def test_check_pull_ready_persists_connection_row(session):
    await _clear_pdd_state(session)
    await session.execute(text(_store_row_sql(305)))
    await session.commit()

    service = PddPullService()
    await service.check_pull_ready(session=session, store_id=305)
    await session.commit()

    stmt = text(
        """
        SELECT id, platform
        FROM store_platform_connections
        WHERE store_id = :store_id AND platform = 'pdd'
        LIMIT 1
        """
    )
    result = await session.execute(stmt, {"store_id": 305})
    row = result.first()

    assert row is not None
    assert row.platform == "pdd"
