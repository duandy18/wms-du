from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.oms.platforms.pdd import service_order_detail as detail_module
from app.oms.platforms.pdd.service_order_detail import (
    PddOrderDetailService,
    PddOrderDetailServiceError,
)
from app.oms.platforms.pdd.service_decrypt import PddDecryptServiceError


@pytest.mark.asyncio
async def test_fetch_order_detail_requires_order_sn(session):
    service = PddOrderDetailService()

    with pytest.raises(PddOrderDetailServiceError) as exc:
        await service.fetch_order_detail(
            session=session,
            store_id=123,
            order_sn="",
        )

    assert "order_sn is required" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_order_detail_requires_store_id_positive(session):
    service = PddOrderDetailService()

    with pytest.raises(PddOrderDetailServiceError) as exc:
        await service.fetch_order_detail(
            session=session,
            store_id=0,
            order_sn="PDD-ORDER-001",
        )

    assert "store_id must be positive" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_order_detail_rejects_missing_credential(session, monkeypatch):
    service = PddOrderDetailService()

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
        assert store_id == 123
        assert platform == "pdd"
        return None

    monkeypatch.setattr(
        detail_module,
        "require_enabled_pdd_app_config",
        _fake_require_enabled_pdd_app_config,
    )
    monkeypatch.setattr(
        detail_module,
        "build_pdd_open_config_from_model",
        _fake_build_pdd_open_config_from_model,
    )
    monkeypatch.setattr(
        detail_module,
        "get_credential_by_store_platform",
        _fake_get_credential_by_store_platform,
    )

    with pytest.raises(PddOrderDetailServiceError) as exc:
        await service.fetch_order_detail(
            session=session,
            store_id=123,
            order_sn="PDD-ORDER-001",
        )

    assert "pdd credential not found" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_order_detail_success_with_decrypt(session, monkeypatch):
    service = PddOrderDetailService()

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
        return _Credential()

    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def post(self, *, api_type: str, business_params: dict):
            captured["api_type"] = api_type
            captured["business_params"] = business_params
            return {
                "order_info_get_response": {
                    "order_info": {
                        "order_sn": "PDD-ORDER-001",
                        "receiver_name": "张*三",
                        "receiver_phone": "138****8888",
                        "address": "上海市**区**路**号",
                        "province": "上海",
                        "city": "上海市",
                        "town": "静安区",
                        "buyer_memo": "麻烦尽快发货",
                        "remark": "老客户，加赠袜子",
                        "data_tag": "tag-001",
                        "item_list": [
                            {
                                "goods_id": "112233",
                                "goods_name": "夏季透气运动鞋",
                                "sku_id": "987654321",
                                "outer_id": "SKU-BLACK-XL",
                                "goods_count": 2,
                                "goods_price": 4950,
                            }
                        ],
                    }
                }
            }

    class _FakeDecryptService:
        def __init__(self, config):
            self.config = config

        async def decrypt_fields(self, *, store_id: int, data_tags: list[str], fields: list[str]):
            assert store_id == 123
            assert data_tags == ["tag-001"]
            assert fields == ["receiver_name", "receiver_phone", "receiver_address"]
            return {
                "receiver_name": "张三",
                "receiver_phone": "13800138000",
                "receiver_address": "上海市静安区世纪大道100号",
            }

    monkeypatch.setattr(
        detail_module,
        "require_enabled_pdd_app_config",
        _fake_require_enabled_pdd_app_config,
    )
    monkeypatch.setattr(
        detail_module,
        "build_pdd_open_config_from_model",
        _fake_build_pdd_open_config_from_model,
    )
    monkeypatch.setattr(
        detail_module,
        "get_credential_by_store_platform",
        _fake_get_credential_by_store_platform,
    )
    monkeypatch.setattr(
        detail_module,
        "PddOpenClient",
        _FakeClient,
    )
    monkeypatch.setattr(
        detail_module,
        "PddDecryptService",
        _FakeDecryptService,
    )

    result = await service.fetch_order_detail(
        session=session,
        store_id=123,
        order_sn="PDD-ORDER-001",
    )

    assert captured["api_type"] == "pdd.order.information.get"
    assert captured["business_params"]["order_sn"] == "PDD-ORDER-001"
    assert captured["business_params"]["access_token"] == "access-token-001"

    assert result.order_sn == "PDD-ORDER-001"
    assert result.province == "上海"
    assert result.city == "上海市"
    assert result.town == "静安区"
    assert result.receiver_name_masked == "张三"
    assert result.receiver_phone_masked == "13800138000"
    assert result.receiver_address_masked == "上海市静安区世纪大道100号"
    assert result.buyer_memo == "麻烦尽快发货"
    assert result.remark == "老客户，加赠袜子"
    assert len(result.items) == 1

    item = result.items[0]
    assert item.goods_id == "112233"
    assert item.goods_name == "夏季透气运动鞋"
    assert item.sku_id == "987654321"
    assert item.outer_id == "SKU-BLACK-XL"
    assert item.goods_count == 2
    assert item.goods_price == 4950


@pytest.mark.asyncio
async def test_fetch_order_detail_decrypt_failure_surfaces_error(session, monkeypatch):
    service = PddOrderDetailService()

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
                "order_info_get_response": {
                    "order_info": {
                        "order_sn": "PDD-ORDER-001",
                        "receiver_name": "张*三",
                        "receiver_phone": "138****8888",
                        "address": "上海市**区**路**号",
                        "province": "上海",
                        "city": "上海市",
                        "town": "静安区",
                        "data_tag": "tag-001",
                        "item_list": [],
                    }
                }
            }

    class _FakeDecryptService:
        def __init__(self, config):
            self.config = config

        async def decrypt_fields(self, *, store_id: int, data_tags: list[str], fields: list[str]):
            raise PddDecryptServiceError("decrypt denied")

    monkeypatch.setattr(
        detail_module,
        "require_enabled_pdd_app_config",
        _fake_require_enabled_pdd_app_config,
    )
    monkeypatch.setattr(
        detail_module,
        "build_pdd_open_config_from_model",
        _fake_build_pdd_open_config_from_model,
    )
    monkeypatch.setattr(
        detail_module,
        "get_credential_by_store_platform",
        _fake_get_credential_by_store_platform,
    )
    monkeypatch.setattr(
        detail_module,
        "PddOpenClient",
        _FakeClient,
    )
    monkeypatch.setattr(
        detail_module,
        "PddDecryptService",
        _FakeDecryptService,
    )

    with pytest.raises(PddOrderDetailServiceError) as exc:
        await service.fetch_order_detail(
            session=session,
            store_id=123,
            order_sn="PDD-ORDER-001",
        )

    assert "Failed to decrypt" in str(exc.value)


@pytest.mark.asyncio
async def test_fetch_order_detail_rejects_missing_order_sn_in_response(session, monkeypatch):
    service = PddOrderDetailService()

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
                "order_info_get_response": {
                    "order_info": {
                        "receiver_name": "张*三",
                    }
                }
            }

    monkeypatch.setattr(
        detail_module,
        "require_enabled_pdd_app_config",
        _fake_require_enabled_pdd_app_config,
    )
    monkeypatch.setattr(
        detail_module,
        "build_pdd_open_config_from_model",
        _fake_build_pdd_open_config_from_model,
    )
    monkeypatch.setattr(
        detail_module,
        "get_credential_by_store_platform",
        _fake_get_credential_by_store_platform,
    )
    monkeypatch.setattr(
        detail_module,
        "PddOpenClient",
        _FakeClient,
    )

    with pytest.raises(PddOrderDetailServiceError) as exc:
        await service.fetch_order_detail(
            session=session,
            store_id=123,
            order_sn="PDD-ORDER-001",
        )

    assert "pdd order detail missing order_sn" in str(exc.value)
