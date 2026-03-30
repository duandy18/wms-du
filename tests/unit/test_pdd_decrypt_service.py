from __future__ import annotations

import pytest

from app.oms.platforms.pdd import service_decrypt as decrypt_module
from app.oms.platforms.pdd.service_decrypt import (
    PddDecryptService,
    PddDecryptServiceError,
)
from app.oms.platforms.pdd.client import PddOpenClientError


class _Config:
    client_id = "pdd-client-id-001"
    client_secret = "pdd-client-secret-001"
    api_base_url = "https://gw-api.pinduoduo.com/api/router"
    sign_method = "md5"


@pytest.mark.asyncio
async def test_decrypt_fields_success(monkeypatch):
    captured = {}

    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def post(self, *, api_type: str, business_params: dict):
            captured["api_type"] = api_type
            captured["business_params"] = business_params
            return {
                "open_decrypt_mask_batch_response": {
                    "result_list": [
                        {
                            "field": "receiver_name",
                            "value": "张三",
                        },
                        {
                            "field": "receiver_phone",
                            "value": "13800138000",
                        },
                        {
                            "field": "receiver_address",
                            "value": "上海市静安区世纪大道100号",
                        },
                    ]
                }
            }

    monkeypatch.setattr(decrypt_module, "PddOpenClient", _FakeClient)

    service = PddDecryptService(config=_Config())
    result = await service.decrypt_fields(
        store_id=123,
        data_tags=["tag-001"],
        fields=["receiver_name", "receiver_phone", "receiver_address"],
    )

    assert captured["api_type"] == "pdd.open.decrypt.mask.batch"
    assert captured["business_params"]["data_tags"] == ["tag-001"]
    assert captured["business_params"]["fields"] == [
        "receiver_name",
        "receiver_phone",
        "receiver_address",
    ]
    assert "open_decrypt_mask_batch_response" in result


@pytest.mark.asyncio
async def test_decrypt_fields_retries_then_success(monkeypatch):
    calls = {"count": 0}

    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def post(self, *, api_type: str, business_params: dict):
            calls["count"] += 1
            if calls["count"] < 3:
                raise PddOpenClientError("frequency limit")
            return {
                "open_decrypt_mask_batch_response": {
                    "result_list": []
                }
            }

    async def _fake_sleep(_seconds: float):
        return None

    monkeypatch.setattr(decrypt_module, "PddOpenClient", _FakeClient)
    monkeypatch.setattr(decrypt_module.asyncio, "sleep", _fake_sleep)

    service = PddDecryptService(config=_Config())
    result = await service.decrypt_fields(
        store_id=123,
        data_tags=["tag-001"],
        fields=["receiver_name"],
    )

    assert calls["count"] == 3
    assert "open_decrypt_mask_batch_response" in result


@pytest.mark.asyncio
async def test_decrypt_fields_raises_after_retries(monkeypatch):
    calls = {"count": 0}

    class _FakeClient:
        def __init__(self, config):
            self.config = config

        async def post(self, *, api_type: str, business_params: dict):
            calls["count"] += 1
            raise PddOpenClientError("decrypt failed")

    async def _fake_sleep(_seconds: float):
        return None

    monkeypatch.setattr(decrypt_module, "PddOpenClient", _FakeClient)
    monkeypatch.setattr(decrypt_module.asyncio, "sleep", _fake_sleep)

    service = PddDecryptService(config=_Config())

    with pytest.raises(PddDecryptServiceError) as exc:
        await service.decrypt_fields(
            store_id=123,
            data_tags=["tag-001"],
            fields=["receiver_name"],
        )

    assert "Decrypt failed" in str(exc.value)
    assert calls["count"] == service.retry_count
