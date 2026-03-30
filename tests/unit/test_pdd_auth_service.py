from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.oms.platforms.pdd import service_auth as pdd_service_auth_module
from app.oms.platforms.pdd.service_auth import (
    PddAuthService,
    PddAuthServiceError,
)
from app.oms.platforms.pdd.settings import PddOpenConfig


def _config() -> PddOpenConfig:
    return PddOpenConfig(
        client_id="pdd-client-id-001",
        client_secret="pdd-client-secret-001",
        api_base_url="https://gw-api.pinduoduo.com/api/router",
        sign_method="md5",
    )


def _service() -> PddAuthService:
    return PddAuthService(
        config=_config(),
        redirect_uri="http://127.0.0.1:8000/oms/pdd/oauth/callback",
    )


def test_build_authorize_url_success():
    service = _service()

    result = service.build_authorize_url(store_id=123)

    assert result.platform == "pdd"
    assert result.store_id == 123
    assert isinstance(result.state, str) and result.state
    assert result.authorize_url.startswith(
        "https://fuwu.pinduoduo.com/service-market/auth?"
    )
    assert "response_type=code" in result.authorize_url
    assert "client_id=pdd-client-id-001" in result.authorize_url
    assert "redirect_uri=" in result.authorize_url
    assert "state=" in result.authorize_url


def test_build_authorize_url_rejects_invalid_store_id():
    service = _service()

    with pytest.raises(PddAuthServiceError) as exc:
        service.build_authorize_url(store_id=0)

    assert "store_id must be positive" in str(exc.value)


def test_parse_state_roundtrip_success():
    service = _service()

    state = service._build_state(store_id=456)
    platform, store_id = service._parse_state(state)

    assert platform == "pdd"
    assert store_id == 456


def test_parse_state_rejects_bad_signature():
    service = _service()

    state = service._build_state(store_id=789)
    payload, _sig = state.split(".", 1)
    bad_state = f"{payload}.deadbeef"

    with pytest.raises(PddAuthServiceError) as exc:
        service._parse_state(bad_state)

    assert "invalid oauth state signature" in str(exc.value)


@pytest.mark.asyncio
async def test_handle_callback_success(session, monkeypatch):
    service = _service()
    state = service._build_state(store_id=321)

    async def _fake_exchange_code_for_token(*, code: str):
        assert code == "test-code-001"
        return {
            "pop_auth_token_create_response": {
                "owner_id": "owner-001",
                "owner_name": "shop-001",
                "access_token": "access-token-001",
                "refresh_token": "refresh-token-001",
                "expires_at": 1893456000,
                "expires_in": 3600,
                "scope": ["pdd.order.list.get", "pdd.goods.list.get"],
                "request_id": "req-001",
            }
        }

    captured_credential = {}
    captured_connection = {}

    async def _fake_upsert_credential_by_store_platform(session, *, data):
        captured_credential["store_id"] = data.store_id
        captured_credential["platform"] = data.platform
        captured_credential["access_token"] = data.access_token
        captured_credential["refresh_token"] = data.refresh_token
        captured_credential["scope"] = data.scope
        captured_credential["granted_identity_type"] = data.granted_identity_type
        captured_credential["granted_identity_value"] = data.granted_identity_value
        captured_credential["granted_identity_display"] = data.granted_identity_display
        captured_credential["raw_payload_json"] = data.raw_payload_json
        return object()

    async def _fake_upsert_connection_by_store_platform(session, *, data):
        captured_connection["store_id"] = data.store_id
        captured_connection["platform"] = data.platform
        captured_connection["auth_source"] = data.auth_source
        captured_connection["connection_status"] = data.connection_status
        captured_connection["credential_status"] = data.credential_status
        captured_connection["reauth_required"] = data.reauth_required
        captured_connection["pull_ready"] = data.pull_ready
        captured_connection["status"] = data.status
        captured_connection["status_reason"] = data.status_reason
        captured_connection["last_authorized_at"] = data.last_authorized_at
        return object()

    monkeypatch.setattr(
        service,
        "_exchange_code_for_token",
        _fake_exchange_code_for_token,
    )
    monkeypatch.setattr(
        pdd_service_auth_module,
        "upsert_credential_by_store_platform",
        _fake_upsert_credential_by_store_platform,
    )
    monkeypatch.setattr(
        pdd_service_auth_module,
        "upsert_connection_by_store_platform",
        _fake_upsert_connection_by_store_platform,
    )

    result = await service.handle_callback(
        session=session,
        code="test-code-001",
        state=state,
    )

    assert result.platform == "pdd"
    assert result.store_id == 321
    assert result.owner_id == "owner-001"
    assert result.owner_name == "shop-001"
    assert result.access_token == "access-token-001"
    assert result.refresh_token == "refresh-token-001"
    assert isinstance(result.expires_at, datetime)
    assert result.expires_at.tzinfo is not None

    assert captured_credential["store_id"] == 321
    assert captured_credential["platform"] == "pdd"
    assert captured_credential["access_token"] == "access-token-001"
    assert captured_credential["refresh_token"] == "refresh-token-001"
    assert captured_credential["scope"] == "pdd.order.list.get,pdd.goods.list.get"
    assert captured_credential["granted_identity_type"] == "pdd_owner_id"
    assert captured_credential["granted_identity_value"] == "owner-001"
    assert captured_credential["granted_identity_display"] == "shop-001"
    assert "pop_auth_token_create_response" in captured_credential["raw_payload_json"]

    assert captured_connection["store_id"] == 321
    assert captured_connection["platform"] == "pdd"
    assert captured_connection["auth_source"] == "oauth"
    assert captured_connection["connection_status"] == "connected"
    assert captured_connection["credential_status"] == "valid"
    assert captured_connection["reauth_required"] is False
    assert captured_connection["pull_ready"] is True
    assert captured_connection["status"] == "connected"
    assert captured_connection["status_reason"] == "authorization_ok"
    assert isinstance(captured_connection["last_authorized_at"], datetime)


@pytest.mark.asyncio
async def test_handle_callback_rejects_missing_access_token(session, monkeypatch):
    service = _service()
    state = service._build_state(store_id=654)

    async def _fake_exchange_code_for_token(*, code: str):
        return {
            "pop_auth_token_create_response": {
                "owner_id": "owner-001",
                "owner_name": "shop-001",
                "refresh_token": "refresh-token-001",
                "expires_at": 1893456000,
            }
        }

    monkeypatch.setattr(
        service,
        "_exchange_code_for_token",
        _fake_exchange_code_for_token,
    )

    with pytest.raises(PddAuthServiceError) as exc:
        await service.handle_callback(
            session=session,
            code="test-code-002",
            state=state,
        )

    assert "pdd oauth token missing access_token" in str(exc.value)


def test_parse_expires_at_falls_back_to_expires_in():
    service = _service()

    value = service._parse_expires_at(
        expires_at=None,
        expires_in=3600,
    )

    assert isinstance(value, datetime)
    assert value.tzinfo == timezone.utc
