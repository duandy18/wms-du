# app/shipping_assist/shipment/waybill_settings.py
from __future__ import annotations

from dataclasses import dataclass

from .contracts import ShipmentApplicationError
from app.core.config import get_settings


@dataclass(frozen=True)
class WaybillTopSettings:
    provider: str
    api_base_url: str
    app_key: str
    app_secret: str
    session: str
    timeout_seconds: float
    sign_method: str
    response_format: str
    version: str


def get_waybill_top_settings() -> WaybillTopSettings:
    settings = get_settings()

    provider = (settings.WAYBILL_PROVIDER or "fake").strip().lower()
    api_base_url = (settings.WAYBILL_TOP_API_BASE_URL or "").strip()
    app_key = (settings.WAYBILL_TOP_APP_KEY or "").strip()
    app_secret = (settings.WAYBILL_TOP_APP_SECRET or "").strip()
    session = (settings.WAYBILL_TOP_SESSION or "").strip()
    sign_method = (settings.WAYBILL_TOP_SIGN_METHOD or "md5").strip().lower()
    response_format = (settings.WAYBILL_TOP_FORMAT or "json").strip().lower()
    version = (settings.WAYBILL_TOP_VERSION or "2.0").strip()
    timeout_seconds = float(settings.WAYBILL_TOP_TIMEOUT_SECONDS)

    if provider not in {"fake", "cainiao_top"}:
        raise ShipmentApplicationError(
            status_code=500,
            code="WAYBILL_PROVIDER_UNSUPPORTED",
            message=f"unsupported waybill provider: {provider}",
        )

    if timeout_seconds <= 0:
        raise ShipmentApplicationError(
            status_code=500,
            code="WAYBILL_TOP_TIMEOUT_INVALID",
            message="WAYBILL_TOP_TIMEOUT_SECONDS must be > 0",
        )

    if sign_method not in {"md5"}:
        raise ShipmentApplicationError(
            status_code=500,
            code="WAYBILL_TOP_SIGN_METHOD_UNSUPPORTED",
            message=f"unsupported sign method: {sign_method}",
        )

    if response_format not in {"json"}:
        raise ShipmentApplicationError(
            status_code=500,
            code="WAYBILL_TOP_FORMAT_UNSUPPORTED",
            message=f"unsupported response format: {response_format}",
        )

    if provider == "cainiao_top":
        missing_fields: list[str] = []
        if not api_base_url:
            missing_fields.append("WAYBILL_TOP_API_BASE_URL")
        if not app_key:
            missing_fields.append("WAYBILL_TOP_APP_KEY")
        if not app_secret:
            missing_fields.append("WAYBILL_TOP_APP_SECRET")
        if not session:
            missing_fields.append("WAYBILL_TOP_SESSION")

        if missing_fields:
            raise ShipmentApplicationError(
                status_code=500,
                code="WAYBILL_TOP_CONFIG_MISSING",
                message="missing waybill top config: " + ", ".join(missing_fields),
            )

    return WaybillTopSettings(
        provider=provider,
        api_base_url=api_base_url,
        app_key=app_key,
        app_secret=app_secret,
        session=session,
        timeout_seconds=timeout_seconds,
        sign_method=sign_method,
        response_format=response_format,
        version=version,
    )
