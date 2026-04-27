from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.platform_order_ingestion.models.pdd_app_config import PddAppConfig
from app.platform_order_ingestion.models.store_platform_connection import StorePlatformConnection
from app.platform_order_ingestion.models.store_platform_credential import StorePlatformCredential
from app.platform_order_ingestion.models.pull_job import (
    PlatformOrderPullJob,
    PlatformOrderPullJobRun,
)

pytestmark = pytest.mark.asyncio


async def _reset_store_status_state(session, *, store_id: int, platform: str) -> None:
    platform_norm = platform.lower()
    await session.execute(
        text(
            """
            DELETE FROM platform_order_pull_job_run_logs
             WHERE run_id IN (
               SELECT id
                 FROM platform_order_pull_job_runs
                WHERE store_id = :sid
             )
            """
        ),
        {"sid": store_id},
    )
    await session.execute(text("DELETE FROM platform_order_pull_job_runs WHERE store_id = :sid"), {"sid": store_id})
    await session.execute(text("DELETE FROM platform_order_pull_jobs WHERE store_id = :sid"), {"sid": store_id})
    await session.execute(
        text("DELETE FROM store_platform_connections WHERE store_id = :sid AND platform = :platform"),
        {"sid": store_id, "platform": platform_norm},
    )
    await session.execute(
        text("DELETE FROM store_platform_credentials WHERE store_id = :sid AND platform = :platform"),
        {"sid": store_id, "platform": platform_norm},
    )
    if platform_norm == "pdd":
        await session.execute(text("DELETE FROM pdd_app_configs"))
    elif platform_norm == "taobao":
        await session.execute(text("DELETE FROM taobao_app_configs"))
    elif platform_norm == "jd":
        await session.execute(text("DELETE FROM jd_app_configs"))
    await session.execute(text("DELETE FROM store_warehouse WHERE store_id = :sid"), {"sid": store_id})
    await session.execute(text("DELETE FROM stores WHERE id = :sid"), {"sid": store_id})
    await session.commit()


async def _seed_store(session, *, store_id: int, platform: str = "PDD", active: bool = True) -> None:
    await session.execute(
        text(
            """
            INSERT INTO stores (id, platform, store_code, store_name, active)
            VALUES (:id, :platform, :store_code, :store_name, :active)
            ON CONFLICT (id) DO UPDATE
              SET platform = EXCLUDED.platform,
                  store_code = EXCLUDED.store_code,
                  store_name = EXCLUDED.store_name,
                  active = EXCLUDED.active
            """
        ),
        {
            "id": store_id,
            "platform": platform,
            "store_code": f"store-{store_id}",
            "store_name": f"store-{store_id}",
            "active": active,
        },
    )
    await session.commit()


async def test_store_status_returns_not_ready_shell_when_no_app_or_auth(client, session):
    store_id = 7301
    await _reset_store_status_state(session, store_id=store_id, platform="pdd")
    await _seed_store(session, store_id=store_id, platform="PDD")

    resp = await client.get(f"/oms/stores/{store_id}/platform-order-ingestion/status")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    data = body["data"]

    assert data["platform"] == "pdd"
    assert data["store"]["id"] == store_id
    assert data["store"]["platform"] == "pdd"
    assert data["store"]["store_code"] == f"store-{store_id}"
    assert data["store"]["active"] is True

    assert data["app"] == {
        "configured": False,
        "enabled_count": 0,
        "status": "not_configured",
    }
    assert data["credential"]["present"] is False
    assert data["credential"]["credential_status"] == "missing"

    assert data["connection"]["present"] is False
    assert data["connection"]["connection_status"] == "not_connected"
    assert data["connection"]["credential_status"] == "missing"
    assert data["connection"]["pull_ready"] is False
    assert data["connection"]["status_reason"] == "authorization_missing"

    assert data["latest_job"] is None
    assert data["pull_ready"] is False
    assert "platform_app_not_ready" in data["blocked_reasons"]
    assert "credential_missing" in data["blocked_reasons"]
    assert "authorization_missing" in data["blocked_reasons"]


async def test_store_status_returns_ready_with_latest_job_and_run(client, session):
    store_id = 7302
    now = datetime.now(timezone.utc)
    await _reset_store_status_state(session, store_id=store_id, platform="pdd")
    await _seed_store(session, store_id=store_id, platform="PDD")

    session.add(
        PddAppConfig(
            client_id="pdd-client-7302",
            client_secret="pdd-secret-7302",
            redirect_uri="http://127.0.0.1:8000/oms/pdd/oauth/callback",
            api_base_url="https://gw-api.pinduoduo.com/api/router",
            sign_method="md5",
            is_enabled=True,
        )
    )
    session.add(
        StorePlatformCredential(
            store_id=store_id,
            platform="pdd",
            credential_type="oauth",
            access_token="access-token-7302",
            refresh_token="refresh-token-7302",
            expires_at=now + timedelta(days=1),
            scope="pdd.order.list.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="pdd_owner_id",
            granted_identity_value="owner-7302",
            granted_identity_display="store-7302",
        )
    )
    session.add(
        StorePlatformConnection(
            store_id=store_id,
            platform="pdd",
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
    await session.flush()

    job = PlatformOrderPullJob(
        platform="pdd",
        store_id=store_id,
        job_type="manual",
        status="success",
        time_from=now - timedelta(hours=1),
        time_to=now,
        order_status=1,
        page_size=50,
        cursor_page=1,
        last_run_at=now,
        last_success_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.flush()

    run = PlatformOrderPullJobRun(
        job_id=job.id,
        platform="pdd",
        store_id=store_id,
        status="success",
        page=1,
        page_size=50,
        has_more=False,
        started_at=now,
        finished_at=now,
        orders_count=2,
        success_count=2,
        failed_count=0,
        request_payload={"page": 1},
        result_payload={"ok": True},
        created_at=now,
    )
    session.add(run)
    await session.commit()

    resp = await client.get(f"/oms/stores/{store_id}/platform-order-ingestion/status")
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["app"]["configured"] is True
    assert data["app"]["status"] == "ready"
    assert data["credential"]["present"] is True
    assert data["credential"]["credential_status"] == "valid"
    assert data["credential"]["expired"] is False
    assert data["credential"]["granted_identity_value"] == "owner-7302"
    assert data["connection"]["present"] is True
    assert data["connection"]["pull_ready"] is True
    assert data["pull_ready"] is True
    assert data["blocked_reasons"] == []

    assert data["latest_job"]["id"] == job.id
    assert data["latest_job"]["status"] == "success"
    assert data["latest_job"]["latest_run"]["id"] == run.id
    assert data["latest_job"]["latest_run"]["orders_count"] == 2
    assert data["latest_job"]["latest_run"]["success_count"] == 2

    assert "access-token-7302" not in resp.text
    assert "refresh-token-7302" not in resp.text


async def test_store_status_expired_credential_blocks_pull_ready_even_if_connection_is_stale_ready(client, session):
    store_id = 7303
    now = datetime.now(timezone.utc)
    await _reset_store_status_state(session, store_id=store_id, platform="pdd")
    await _seed_store(session, store_id=store_id, platform="PDD")

    session.add(
        PddAppConfig(
            client_id="pdd-client-7303",
            client_secret="pdd-secret-7303",
            redirect_uri="http://127.0.0.1:8000/oms/pdd/oauth/callback",
            api_base_url="https://gw-api.pinduoduo.com/api/router",
            sign_method="md5",
            is_enabled=True,
        )
    )
    session.add(
        StorePlatformCredential(
            store_id=store_id,
            platform="pdd",
            credential_type="oauth",
            access_token="expired-token-7303",
            refresh_token="refresh-token-7303",
            expires_at=now - timedelta(minutes=5),
            scope="pdd.order.list.get",
            raw_payload_json={"source": "test"},
            granted_identity_type="pdd_owner_id",
            granted_identity_value="owner-7303",
            granted_identity_display="store-7303",
        )
    )
    session.add(
        StorePlatformConnection(
            store_id=store_id,
            platform="pdd",
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

    resp = await client.get(f"/oms/stores/{store_id}/platform-order-ingestion/status")
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["app"]["status"] == "ready"
    assert data["credential"]["credential_status"] == "expired"
    assert data["credential"]["expired"] is True
    assert data["connection"]["pull_ready"] is True
    assert data["pull_ready"] is False
    assert "credential_expired" in data["blocked_reasons"]


async def test_store_status_returns_404_when_store_missing(client, session):
    store_id = 7399
    await _reset_store_status_state(session, store_id=store_id, platform="pdd")

    resp = await client.get(f"/oms/stores/{store_id}/platform-order-ingestion/status")
    assert resp.status_code == 404, resp.text
    assert "store not found" in resp.text
