# app/wms/system/sso_v1/services/sso_exchange_service.py
from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.user.helpers.auth import token_expires_in_seconds
from app.user.models.user import User
from app.user.services.user_service import UserService
from app.wms.system.sso_v1.contracts import (
    ErpSsoAuthorizationCodeConsumeOut,
    WmsSsoExchangeIn,
    WmsSsoExchangeOut,
)
from app.wms.system.sso_v1.services.erp_sso_authorization_code_client import (
    ErpSsoAuthorizationCodeClient,
    ErpSsoAuthorizationCodeClientError,
)


class WmsSsoBindingRequiredError(ValueError):
    pass


class WmsSsoErpExchangeFailedError(ValueError):
    pass


class WmsSsoAppMismatchError(ValueError):
    pass


class WmsSsoUserNotFoundError(ValueError):
    pass


class WmsSsoUserInactiveError(ValueError):
    pass


class ErpSsoAuthorizationCodeClientLike(Protocol):
    async def consume_authorization_code(
        self,
        *,
        code: str,
        state: str,
        binding: str,
    ) -> ErpSsoAuthorizationCodeConsumeOut:
        ...


class UserServiceLike(Protocol):
    def get_user_by_username(self, username: str) -> User | None:
        ...

    def create_token_for_user(self, user: User) -> str:
        ...


class WmsSsoExchangeService:
    """
    Exchange ERP SSO authorization code for WMS local token.

    Boundary:
    - Does not create WMS users.
    - Does not create WMS permissions.
    - Does not accept ERP token as WMS token.
    - WMS local token and local user/permission checks remain authoritative.
    """

    def __init__(
        self,
        db: Session,
        *,
        erp_client: ErpSsoAuthorizationCodeClientLike | None = None,
        user_service: UserServiceLike | None = None,
    ) -> None:
        self.erp_client = erp_client or ErpSsoAuthorizationCodeClient()
        self.user_service = user_service or UserService(db)

    async def exchange(
        self,
        payload: WmsSsoExchangeIn,
        *,
        binding: str | None,
    ) -> WmsSsoExchangeOut:
        normalized_binding = _strip(binding)
        if not normalized_binding:
            raise WmsSsoBindingRequiredError("wms_sso_binding_required")

        try:
            identity = await self.erp_client.consume_authorization_code(
                code=_strip(payload.code),
                state=_strip(payload.state),
                binding=normalized_binding,
            )
        except ErpSsoAuthorizationCodeClientError as exc:
            raise WmsSsoErpExchangeFailedError("wms_sso_erp_exchange_failed") from exc

        if identity.app_code != "wms":
            raise WmsSsoAppMismatchError("wms_sso_app_mismatch")

        user = self.user_service.get_user_by_username(identity.username)
        if user is None:
            raise WmsSsoUserNotFoundError("wms_sso_user_not_found")

        if not bool(getattr(user, "is_active", True)):
            raise WmsSsoUserInactiveError("wms_sso_user_inactive")

        access_token = self.user_service.create_token_for_user(user)

        return WmsSsoExchangeOut(
            access_token=access_token,
            token_type="bearer",
            expires_in=token_expires_in_seconds(),
            redirect_path=identity.redirect_path or "/",
        )


def _strip(value: str | None) -> str:
    return (value or "").strip()


__all__ = [
    "ErpSsoAuthorizationCodeClientLike",
    "UserServiceLike",
    "WmsSsoAppMismatchError",
    "WmsSsoBindingRequiredError",
    "WmsSsoErpExchangeFailedError",
    "WmsSsoExchangeService",
    "WmsSsoUserInactiveError",
    "WmsSsoUserNotFoundError",
]
