# app/tms/shipment/waybill_gateway_factory.py
from __future__ import annotations

from .waybill_gateway_fake import FakeWaybillGateway
from .waybill_settings import get_waybill_top_settings
from .waybill_service import WaybillProvider


def get_waybill_provider() -> WaybillProvider:
    settings = get_waybill_top_settings()

    if settings.provider == "fake":
        return FakeWaybillGateway()

    if settings.provider == "cainiao_top":
        from .waybill_gateway_cainiao import CainiaoTopWaybillGateway

        return CainiaoTopWaybillGateway(settings)

    raise RuntimeError(f"unsupported waybill provider: {settings.provider}")
