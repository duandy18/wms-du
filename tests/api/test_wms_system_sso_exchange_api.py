from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.wms.system.sso_v1.contracts import WmsSsoExchangeIn, WmsSsoExchangeOut
from app.wms.system.sso_v1.routers.exchange import get_wms_sso_exchange_service
from app.wms.system.sso_v1.services import ERP_SSO_BINDING_COOKIE_NAME
from app.wms.system.sso_v1.services.sso_exchange_service import (
    WmsSsoBindingRequiredError,
)

PATH = "/system/sso/v1/exchange"


class FakeExchangeService:
    def __init__(self) -> None:
        self.payload: WmsSsoExchangeIn | None = None
        self.binding: str | None = None

    async def exchange(
        self,
        payload: WmsSsoExchangeIn,
        *,
        binding: str | None,
    ) -> WmsSsoExchangeOut:
        self.payload = payload
        self.binding = binding
        if not binding:
            raise WmsSsoBindingRequiredError("wms_sso_binding_required")
        return WmsSsoExchangeOut(
            access_token="wms-local-token",
            token_type="bearer",
            expires_in=3600,
            redirect_path="/",
        )


def test_wms_sso_exchange_route_returns_local_token() -> None:
    fake = FakeExchangeService()
    app.dependency_overrides[get_wms_sso_exchange_service] = lambda: fake

    try:
        client = TestClient(app)
        client.cookies.set(ERP_SSO_BINDING_COOKIE_NAME, "binding-value")
        response = client.post(
            PATH,
            json={
                "code": "code-value",
                "state": "state-value",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "access_token": "wms-local-token",
        "token_type": "bearer",
        "expires_in": 3600,
        "redirect_path": "/",
    }
    assert fake.payload is not None
    assert fake.payload.code == "code-value"
    assert fake.payload.state == "state-value"
    assert fake.binding == "binding-value"


def test_wms_sso_exchange_route_requires_binding_cookie() -> None:
    fake = FakeExchangeService()
    app.dependency_overrides[get_wms_sso_exchange_service] = lambda: fake

    try:
        client = TestClient(app)
        response = client.post(
            PATH,
            json={
                "code": "code-value",
                "state": "state-value",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "wms_sso_binding_required" in response.text


def test_wms_sso_exchange_route_is_registered_in_openapi() -> None:
    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    assert PATH in paths
    assert "post" in paths[PATH]
