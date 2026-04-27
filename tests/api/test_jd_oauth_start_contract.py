from __future__ import annotations

import pytest
from sqlalchemy import text

from app.platform_order_ingestion.jd.repository import (
    JdAppConfigUpsertInput,
    upsert_current_jd_app_config,
)


pytestmark = pytest.mark.asyncio


async def _clear_jd_app_configs(session) -> None:
    await session.execute(text("DELETE FROM jd_app_configs"))
    await session.commit()


async def _seed_jd_app_config(session) -> None:
    await upsert_current_jd_app_config(
        session,
        data=JdAppConfigUpsertInput(
            client_id="jd-client-id-001",
            client_secret="jd-client-secret-001",
            callback_url="http://127.0.0.1:8000/oms/jd/oauth/callback",
            gateway_url="https://api.jd.com/routerjson",
            sign_method="md5",
            is_enabled=True,
        ),
    )
    await session.commit()


@pytest.mark.asyncio
async def test_jd_oauth_start_returns_authorize_url(client, session):
    await _clear_jd_app_configs(session)
    await _seed_jd_app_config(session)

    resp = await client.get("/oms/jd/oauth/start", params={"store_id": 101})
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["ok"] is True
    data = body["data"]

    assert data["platform"] == "jd"
    assert data["store_id"] == 101
    assert isinstance(data["state"], str) and data["state"]
    assert isinstance(data["authorize_url"], str) and data["authorize_url"]
    assert data["authorize_url"].startswith("https://open-oauth.jd.com/oauth2/to_login?")
    assert "response_type=code" in data["authorize_url"]
    assert "client_id=jd-client-id-001" in data["authorize_url"]
    assert "redirect_uri=" in data["authorize_url"]
    assert "state=" in data["authorize_url"]


@pytest.mark.asyncio
async def test_jd_oauth_start_requires_enabled_app_config(client, session):
    await _clear_jd_app_configs(session)

    resp = await client.get("/oms/jd/oauth/start", params={"store_id": 101})
    assert resp.status_code == 400, resp.text
    assert "enabled jd app config not found" in resp.text
