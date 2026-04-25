# app/shipping_assist/shipment/waybill_top_client.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

import httpx

from .contracts import ShipmentApplicationError
from .waybill_settings import WaybillTopSettings
from .waybill_top_sign import build_top_sign

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TopApiCallResult:
    request_params: dict[str, Any]
    response_json: dict[str, Any]


class TopApiClient:
    def __init__(self, settings: WaybillTopSettings) -> None:
        self.settings = settings

    async def post(
        self,
        *,
        method: str,
        business_params: Mapping[str, Any],
    ) -> TopApiCallResult:
        public_params = self._build_public_params(method=method)
        payload: dict[str, Any] = dict(public_params)
        payload.update(dict(business_params))
        payload["sign"] = build_top_sign(payload, self.settings.app_secret)

        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                response = await client.post(
                    self.settings.api_base_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "TOP API http status error: method=%s status=%s",
                method,
                exc.response.status_code,
            )
            raise ShipmentApplicationError(
                status_code=502,
                code="WAYBILL_TOP_HTTP_STATUS_ERROR",
                message=f"top api http status error: {exc.response.status_code}",
            ) from exc
        except httpx.RequestError as exc:
            logger.exception("TOP API request error: method=%s", method)
            raise ShipmentApplicationError(
                status_code=502,
                code="WAYBILL_TOP_REQUEST_ERROR",
                message=f"top api request error: {exc}",
            ) from exc

        try:
            response_json = response.json()
        except json.JSONDecodeError as exc:
            logger.exception("TOP API invalid json response: method=%s", method)
            raise ShipmentApplicationError(
                status_code=502,
                code="WAYBILL_TOP_INVALID_JSON",
                message="top api returned invalid json response",
            ) from exc

        if not isinstance(response_json, dict):
            raise ShipmentApplicationError(
                status_code=502,
                code="WAYBILL_TOP_INVALID_RESPONSE",
                message="top api returned non-object json response",
            )

        error_response = response_json.get("error_response")
        if isinstance(error_response, dict):
            sub_code = str(error_response.get("sub_code") or error_response.get("code") or "")
            sub_msg = str(
                error_response.get("sub_msg")
                or error_response.get("msg")
                or "top api returned error_response"
            )
            logger.error(
                "TOP API business error: method=%s code=%s msg=%s",
                method,
                sub_code,
                sub_msg,
            )
            raise ShipmentApplicationError(
                status_code=502,
                code="WAYBILL_TOP_ERROR_RESPONSE",
                message=f"{sub_code} {sub_msg}".strip(),
            )

        return TopApiCallResult(
            request_params=self._mask_payload(payload),
            response_json=response_json,
        )

    def _build_public_params(self, *, method: str) -> dict[str, Any]:
        return {
            "method": method,
            "app_key": self.settings.app_key,
            "session": self.settings.session,
            "format": self.settings.response_format,
            "v": self.settings.version,
            "sign_method": self.settings.sign_method,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    @staticmethod
    def _mask_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        masked = dict(payload)
        if "session" in masked and masked["session"]:
            masked["session"] = "***"
        if "sign" in masked and masked["sign"]:
            masked["sign"] = "***"
        return masked
