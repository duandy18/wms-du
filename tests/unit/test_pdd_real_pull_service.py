from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.oms.platforms.pdd import service_real_pull as real_pull_module
from app.oms.platforms.pdd.service_real_pull import (
    PddRealPullParams,
    PddRealPullService,
    PddRealPullServiceError,
)


@pytest.mark.asyncio
async def test_fetch_order_page_rejects_invalid_time_window(session, monkeypatch):
    service = PddRealPullService()

    params = PddRealPullParams(
        store_id=123,
        start_confirm_at="2026-03-29 10:00:00",
        end_confirm_at="2026-03-29 09:00:00",
        order_status=1,
        page=1,
        page_size=50,
    )

    with pytest.raises(PddRealPullServiceError) as exc:
        await service.fetch_order_page(session=session, params=params)

    assert "end_confirm_at must be greater than start_confirm_at" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_order_page_rejects_window_too_large(session, monkeypatch):
    service = PddRealPullService()

    params = PddRealPullParams(
        store_id=123,
        start_confirm_at="2026-03-27 00:00:00",
        end_confirm_at="2026-03-29 12:00:00",
        order_status=1,
        page=1,
        page_size=50,
    )

    with pytest.raises(PddRealPullServiceError) as exc:
        await service.fetch_order_page(session=session, params=params)

    assert "time window must be <= 24 hours" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_order_page_rejects_invalid_page_size(session, monkeypatch):
    service = PddRealPullService()

    params = PddRealPullParams(
        store_id=123,
        start_confirm_at="2026-03-29 00:00:00",
        end_confirm_at="2026-03-29 23:59:59",
        order_status=1,
        page=1,
        page_size=150,
    )

    with pytest.raises(PddRealPullServiceError) as exc:
        await service.fetch_order_page(session=session, params=params)

    assert "page_size must be <= 100" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_order_page_uses_default_window_when_missing(session, monkeypatch):
    service = PddRealPullService()

    class _AppConfig:
        pass

    class _Config:
        client_id = "pdd-client-id-001"
        client_secret = "pdd-client-secret-001"
        api_base_url = "https://gw-api.pinduoduo.com/api/router"
        sign_method = "md5"

    class _Credential:
        access_token = "access-token-001"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    captured = {}

    async def _fake_require_enabled_pdd_app_config(session):
        return _AppConfig()

    def _fake_build_pdd_open_config_from_model(row):
        return _Config()

    async def _fake_get_credential_by_store_platform(session, *, store_id: int, platform: str):
        assert store_id == 123
        assert platform == "pdd"
        return _Credential()

    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def post(self, *, api_type: str, business_params: dict):
            captured["api_type"] = api_type
            captured["business_params"] = business_params
            return {
                "order_list_get_response": {
                    "order_list": [],
                    "has_more": False,
                }
            }

    monkeypatch.setattr(
        real_pull_module,
        "require_enabled_pdd_app_config",
        _fake_require_enabled_pdd_app_config,
    )
    monkeypatch.setattr(
        real_pull_module,
        "build_pdd_open_config_from_model",
        _fake_build_pdd_open_config_from_model,
    )
    monkeypatch.setattr(
        real_pull_module,
        "get_credential_by_store_platform",
        _fake_get_credential_by_store_platform,
    )
    monkeypatch.setattr(
        real_pull_module,
        "PddOpenClient",
        _FakeClient,
    )

    params = PddRealPullParams(store_id=123)

    result = await service.fetch_order_page(session=session, params=params)

    assert result.page == 1
    assert result.page_size == 50
    assert result.orders_count == 0
    assert result.has_more is False
    assert result.orders == []

    assert captured["api_type"] == "pdd.order.list.get"
    assert captured["business_params"]["access_token"] == "access-token-001"
    assert captured["business_params"]["order_status"] == 1
    assert captured["business_params"]["page"] == 1
    assert captured["business_params"]["page_size"] == 50
    assert isinstance(captured["business_params"]["start_confirm_at"], str)
    assert isinstance(captured["business_params"]["end_confirm_at"], str)


@pytest.mark.asyncio
async def test_fetch_order_page_success_parses_orders(session, monkeypatch):
    service = PddRealPullService()

    class _AppConfig:
        pass

    class _Config:
        client_id = "pdd-client-id-001"
        client_secret = "pdd-client-secret-001"
        api_base_url = "https://gw-api.pinduoduo.com/api/router"
        sign_method = "md5"

    class _Credential:
        access_token = "access-token-001"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    async def _fake_require_enabled_pdd_app_config(session):
        return _AppConfig()

    def _fake_build_pdd_open_config_from_model(row):
        return _Config()

    async def _fake_get_credential_by_store_platform(session, *, store_id: int, platform: str):
        return _Credential()

    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def post(self, *, api_type: str, business_params: dict):
            return {
                "order_list_get_response": {
                    "order_list": [
                        {
                            "order_sn": "PDD-ORDER-001",
                            "order_status": 1,
                            "confirm_time": "2026-03-29 12:00:00",
                            "receiver_name": "张**",
                            "receiver_mobile": "138****0000",
                            "province": "上海市",
                            "city": "上海市",
                            "district": "浦东新区",
                            "address": "世纪大道***号",
                            "buyer_memo": "尽快发货",
                            "item_list": [{"sku": "A"}, {"sku": "B"}],
                        }
                    ],
                    "has_more": False,
                }
            }

    monkeypatch.setattr(
        real_pull_module,
        "require_enabled_pdd_app_config",
        _fake_require_enabled_pdd_app_config,
    )
    monkeypatch.setattr(
        real_pull_module,
        "build_pdd_open_config_from_model",
        _fake_build_pdd_open_config_from_model,
    )
    monkeypatch.setattr(
        real_pull_module,
        "get_credential_by_store_platform",
        _fake_get_credential_by_store_platform,
    )
    monkeypatch.setattr(
        real_pull_module,
        "PddOpenClient",
        _FakeClient,
    )

    params = PddRealPullParams(
        store_id=123,
        start_confirm_at="2026-03-29 11:00:00",
        end_confirm_at="2026-03-29 12:30:00",
        order_status=1,
        page=1,
        page_size=50,
    )

    result = await service.fetch_order_page(session=session, params=params)

    assert result.page == 1
    assert result.page_size == 50
    assert result.orders_count == 1
    assert result.has_more is False
    assert len(result.orders) == 1

    order = result.orders[0]
    assert order.platform_order_id == "PDD-ORDER-001"
    assert order.order_status == 1
    assert order.confirm_at == "2026-03-29 12:00:00"
    assert order.receiver_name_masked == "张**"
    assert order.receiver_phone_masked == "138****0000"
    assert order.receiver_address_summary_masked == "上海市上海市浦东新区世纪大道***号"
    assert order.buyer_memo == "尽快发货"
    assert order.items_count == 2


@pytest.mark.asyncio
async def test_fetch_order_page_rejects_missing_credential(session, monkeypatch):
    service = PddRealPullService()

    class _AppConfig:
        pass

    class _Config:
        client_id = "pdd-client-id-001"
        client_secret = "pdd-client-secret-001"
        api_base_url = "https://gw-api.pinduoduo.com/api/router"
        sign_method = "md5"

    async def _fake_require_enabled_pdd_app_config(session):
        return _AppConfig()

    def _fake_build_pdd_open_config_from_model(row):
        return _Config()

    async def _fake_get_credential_by_store_platform(session, *, store_id: int, platform: str):
        return None

    monkeypatch.setattr(
        real_pull_module,
        "require_enabled_pdd_app_config",
        _fake_require_enabled_pdd_app_config,
    )
    monkeypatch.setattr(
        real_pull_module,
        "build_pdd_open_config_from_model",
        _fake_build_pdd_open_config_from_model,
    )
    monkeypatch.setattr(
        real_pull_module,
        "get_credential_by_store_platform",
        _fake_get_credential_by_store_platform,
    )

    params = PddRealPullParams(
        store_id=123,
        start_confirm_at="2026-03-29 00:00:00",
        end_confirm_at="2026-03-29 01:00:00",
    )

    with pytest.raises(PddRealPullServiceError) as exc:
        await service.fetch_order_page(session=session, params=params)

    assert "pdd credential not found" in str(exc.value)
