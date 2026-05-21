# app/wms/system/sso_v1/services/erp_sso_authorization_code_client.py
from __future__ import annotations

import os
from typing import Any

import httpx

from app.wms.system.sso_v1.contracts import ErpSsoAuthorizationCodeConsumeOut

ERP_SERVICE_CLIENT_HEADER = "X-Service-Client"
WMS_SERVICE_CLIENT_CODE = "wms-service"
ERP_SSO_BINDING_COOKIE_NAME = "ERP_SSO_BINDING"
ERP_SSO_AUTHORIZATION_CODE_CONSUME_PATH = (
    "/system/sso/v1/authorization-codes/consume"
)
DEFAULT_ERP_API_BASE_URL = "http://127.0.0.1:7990"


class ErpSsoAuthorizationCodeClientError(RuntimeError):
    pass


class ErpSsoAuthorizationCodeClient:
    """
    WMS -> ERP SSO authorization-code consume client.

    Boundary:
    - WMS calls ERP as fixed service client: wms-service.
    - WMS does not read ERP token or ERP localStorage.
    - ERP returns identity summary only; WMS still signs its own local token.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("ERP_API_BASE_URL")
            or DEFAULT_ERP_API_BASE_URL
        ).rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.transport = transport

    async def consume_authorization_code(
        self,
        *,
        code: str,
        state: str,
        binding: str,
    ) -> ErpSsoAuthorizationCodeConsumeOut:
        url = f"{self.base_url}{ERP_SSO_AUTHORIZATION_CODE_CONSUME_PATH}"
        headers = {
            ERP_SERVICE_CLIENT_HEADER: WMS_SERVICE_CLIENT_CODE,
        }
        payload: dict[str, str] = {
            "code": code,
            "state": state,
            "binding": binding,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                raise ErpSsoAuthorizationCodeClientError(
                    "erp_sso_consume_request_failed"
                ) from exc

        if response.status_code >= 400:
            detail = _response_detail(response)
            raise ErpSsoAuthorizationCodeClientError(
                f"erp_sso_consume_failed:{response.status_code}:{detail}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ErpSsoAuthorizationCodeClientError(
                "erp_sso_consume_invalid_json"
            ) from exc

        try:
            return ErpSsoAuthorizationCodeConsumeOut.model_validate(data)
        except Exception as exc:
            raise ErpSsoAuthorizationCodeClientError(
                "erp_sso_consume_invalid_contract"
            ) from exc


def _response_detail(response: httpx.Response) -> str:
    try:
        data: Any = response.json()
    except ValueError:
        return response.text[:300]

    if isinstance(data, dict):
        detail = data.get("detail")
        if detail is not None:
            return str(detail)[:300]

    return str(data)[:300]


__all__ = [
    "DEFAULT_ERP_API_BASE_URL",
    "ERP_SERVICE_CLIENT_HEADER",
    "ERP_SSO_AUTHORIZATION_CODE_CONSUME_PATH",
    "ERP_SSO_BINDING_COOKIE_NAME",
    "ErpSsoAuthorizationCodeClient",
    "ErpSsoAuthorizationCodeClientError",
    "WMS_SERVICE_CLIENT_CODE",
]
