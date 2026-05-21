from __future__ import annotations

import httpx
import pytest

from app.wms.system.sso_v1.services import (
    ERP_SERVICE_CLIENT_HEADER,
    ERP_SSO_AUTHORIZATION_CODE_CONSUME_PATH,
    WMS_SERVICE_CLIENT_CODE,
    ErpSsoAuthorizationCodeClient,
    ErpSsoAuthorizationCodeClientError,
)


@pytest.mark.asyncio
async def test_erp_sso_authorization_code_client_consumes_with_wms_service_client() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["service_client"] = request.headers.get(ERP_SERVICE_CLIENT_HEADER)
        captured["json"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "app_code": "wms",
                "sub": "erp:user:1",
                "erp_user_id": 1,
                "username": "admin",
                "full_name": "系统管理员",
                "email": None,
                "phone": None,
                "redirect_path": "/",
            },
        )

    client = ErpSsoAuthorizationCodeClient(
        base_url="http://erp-api.test/api/erp",
        transport=httpx.MockTransport(handler),
    )

    result = await client.consume_authorization_code(
        code="code-value",
        state="state-value",
        binding="binding-value",
    )

    assert result.app_code == "wms"
    assert result.username == "admin"
    assert captured["method"] == "POST"
    assert captured["url"] == (
        "http://erp-api.test/api/erp"
        f"{ERP_SSO_AUTHORIZATION_CODE_CONSUME_PATH}"
    )
    assert captured["service_client"] == WMS_SERVICE_CLIENT_CODE
    assert '"code":"code-value"' in str(captured["json"])
    assert '"state":"state-value"' in str(captured["json"])
    assert '"binding":"binding-value"' in str(captured["json"])


@pytest.mark.asyncio
async def test_erp_sso_authorization_code_client_raises_on_erp_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            410,
            json={
                "detail": "sso_authorization_code_expired",
            },
        )

    client = ErpSsoAuthorizationCodeClient(
        base_url="http://erp-api.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ErpSsoAuthorizationCodeClientError):
        await client.consume_authorization_code(
            code="code-value",
            state="state-value",
            binding="binding-value",
        )
