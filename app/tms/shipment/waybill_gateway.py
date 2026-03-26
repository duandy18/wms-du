# app/tms/shipment/waybill_gateway.py
# 分拆说明：
# - 本文件从 service.py 中拆出 Shipment 面单请求边界；
# - 目标是把外部协作（Waybill provider）与应用编排隔离，
#   便于后续从 fake 实现切换到真实平台 OpenAPI。
from __future__ import annotations

from .contracts import ShipmentApplicationError
from .waybill_gateway_factory import get_waybill_provider
from .waybill_service import WaybillRequest, WaybillResult


async def request_waybill(
    *,
    shipping_provider_id: int,
    provider_code: str | None,
    company_code: str | None,
    customer_code: str | None,
    platform: str,
    shop_id: str,
    ext_order_no: str,
    package_no: int,
    sender: dict | None,
    receiver_name: str | None,
    receiver_phone: str | None,
    province: str | None,
    city: str | None,
    district: str | None,
    address_detail: str | None,
    weight_kg: float,
) -> WaybillResult:
    provider = get_waybill_provider()

    req = WaybillRequest(
        shipping_provider_id=shipping_provider_id,
        provider_code=provider_code,
        company_code=company_code,
        customer_code=customer_code,
        platform=platform.upper(),
        shop_id=shop_id,
        ext_order_no=ext_order_no,
        sender=sender,
        receiver={
            "name": receiver_name,
            "phone": receiver_phone,
            "province": province,
            "city": city,
            "district": district,
            "detail": address_detail,
        },
        cargo={"weight_kg": float(weight_kg)},
        extras={"package_no": int(package_no)},
    )

    result = await provider.request_waybill(req)
    if not result.ok or not result.tracking_no:
        raise ShipmentApplicationError(
            status_code=502,
            code="SHIP_WITH_WAYBILL_REQUEST_FAILED",
            message=(
                f"waybill request failed: "
                f"{result.error_code or ''} {result.error_message or ''}"
            ).strip(),
        )
    return result
