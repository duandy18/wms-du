from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.wms.system.sso_v1.contracts import (
    ErpSsoAuthorizationCodeConsumeOut,
    WmsSsoExchangeIn,
)
from app.wms.system.sso_v1.services import ErpSsoAuthorizationCodeClientError
from app.wms.system.sso_v1.services.sso_exchange_service import (
    WmsSsoAppMismatchError,
    WmsSsoBindingRequiredError,
    WmsSsoErpExchangeFailedError,
    WmsSsoExchangeService,
    WmsSsoUserInactiveError,
    WmsSsoUserNotFoundError,
)


class FakeErpClient:
    def __init__(
        self,
        identity: ErpSsoAuthorizationCodeConsumeOut | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.identity = identity or ErpSsoAuthorizationCodeConsumeOut(
            app_code="wms",
            sub="erp:user:1",
            erp_user_id=1,
            username="admin",
            full_name="系统管理员",
            email=None,
            phone=None,
            redirect_path="/",
        )
        self.fail = fail
        self.seen: dict[str, str] = {}

    async def consume_authorization_code(
        self,
        *,
        code: str,
        state: str,
        binding: str,
    ) -> ErpSsoAuthorizationCodeConsumeOut:
        if self.fail:
            raise ErpSsoAuthorizationCodeClientError("erp failed")

        self.seen = {
            "code": code,
            "state": state,
            "binding": binding,
        }
        return self.identity


class FakeUserService:
    def __init__(self, user: object | None = None) -> None:
        self.user = user
        self.token_user: object | None = None

    def get_user_by_username(self, username: str):
        if self.user is None:
            return None
        if getattr(self.user, "username", None) == username:
            return self.user
        return None

    def create_token_for_user(self, user) -> str:
        self.token_user = user
        return "wms-local-token"


@pytest.mark.asyncio
async def test_wms_sso_exchange_service_returns_wms_local_token() -> None:
    erp_client = FakeErpClient()
    user = SimpleNamespace(id=1, username="admin", is_active=True)
    user_service = FakeUserService(user)
    service = WmsSsoExchangeService(
        SimpleNamespace(),
        erp_client=erp_client,
        user_service=user_service,
    )

    payload = await service.exchange(
        WmsSsoExchangeIn(code="code-value", state="state-value"),
        binding="binding-value",
    )

    assert payload.access_token == "wms-local-token"
    assert payload.token_type == "bearer"
    assert payload.expires_in > 0
    assert payload.redirect_path == "/"
    assert erp_client.seen == {
        "code": "code-value",
        "state": "state-value",
        "binding": "binding-value",
    }
    assert user_service.token_user is user


@pytest.mark.asyncio
async def test_wms_sso_exchange_service_requires_binding() -> None:
    service = WmsSsoExchangeService(
        SimpleNamespace(),
        erp_client=FakeErpClient(),
        user_service=FakeUserService(SimpleNamespace(username="admin", is_active=True)),
    )

    with pytest.raises(WmsSsoBindingRequiredError):
        await service.exchange(
            WmsSsoExchangeIn(code="code-value", state="state-value"),
            binding=None,
        )


@pytest.mark.asyncio
async def test_wms_sso_exchange_service_rejects_erp_failure() -> None:
    service = WmsSsoExchangeService(
        SimpleNamespace(),
        erp_client=FakeErpClient(fail=True),
        user_service=FakeUserService(SimpleNamespace(username="admin", is_active=True)),
    )

    with pytest.raises(WmsSsoErpExchangeFailedError):
        await service.exchange(
            WmsSsoExchangeIn(code="code-value", state="state-value"),
            binding="binding-value",
        )


@pytest.mark.asyncio
async def test_wms_sso_exchange_service_rejects_non_wms_identity() -> None:
    erp_client = FakeErpClient(
        ErpSsoAuthorizationCodeConsumeOut(
            app_code="pms",
            sub="erp:user:1",
            erp_user_id=1,
            username="admin",
            redirect_path="/",
        )
    )
    service = WmsSsoExchangeService(
        SimpleNamespace(),
        erp_client=erp_client,
        user_service=FakeUserService(SimpleNamespace(username="admin", is_active=True)),
    )

    with pytest.raises(WmsSsoAppMismatchError):
        await service.exchange(
            WmsSsoExchangeIn(code="code-value", state="state-value"),
            binding="binding-value",
        )


@pytest.mark.asyncio
async def test_wms_sso_exchange_service_rejects_missing_local_user() -> None:
    service = WmsSsoExchangeService(
        SimpleNamespace(),
        erp_client=FakeErpClient(),
        user_service=FakeUserService(None),
    )

    with pytest.raises(WmsSsoUserNotFoundError):
        await service.exchange(
            WmsSsoExchangeIn(code="code-value", state="state-value"),
            binding="binding-value",
        )


@pytest.mark.asyncio
async def test_wms_sso_exchange_service_rejects_inactive_local_user() -> None:
    user = SimpleNamespace(id=1, username="admin", is_active=False)
    service = WmsSsoExchangeService(
        SimpleNamespace(),
        erp_client=FakeErpClient(),
        user_service=FakeUserService(user),
    )

    with pytest.raises(WmsSsoUserInactiveError):
        await service.exchange(
            WmsSsoExchangeIn(code="code-value", state="state-value"),
            binding="binding-value",
        )
