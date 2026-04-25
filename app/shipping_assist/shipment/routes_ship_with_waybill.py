# app/shipping_assist/shipment/routes_ship_with_waybill.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.shipping_assist.shipment import (
    ShipmentApplicationError,
    ShipWithWaybillCommand,
    TransportShipmentService,
)
from app.shipping_assist.shipment.api_contracts import (
    ShipWithWaybillRequest,
    ShipWithWaybillResponse,
)
from app.shipping_assist.shipment.router_helpers import get_order_ref_and_trace_id


def register(router: APIRouter) -> None:
    @router.post(
        "/{platform}/{shop_id}/{ext_order_no}/ship-with-waybill",
        response_model=ShipWithWaybillResponse,
    )
    async def order_ship_with_waybill(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        body: ShipWithWaybillRequest,
        session: AsyncSession = Depends(get_session),
    ) -> ShipWithWaybillResponse:
        platform_norm = platform.upper()
        order_ref, trace_id = await get_order_ref_and_trace_id(
            session=session,
            platform=platform_norm,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )

        shipment_svc = TransportShipmentService(session)
        command = ShipWithWaybillCommand(
            order_ref=order_ref,
            trace_id=trace_id,
            platform=platform_norm,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            package_no=int(body.package_no),
            receiver_name=body.receiver_name,
            receiver_phone=body.receiver_phone,
            province=body.province,
            city=body.city,
            district=body.district,
            address_detail=body.address_detail,
            meta=dict(body.meta.extra) if body.meta else {},
        )

        try:
            result = await shipment_svc.ship_with_waybill(command)
        except ShipmentApplicationError as error:
            raise HTTPException(status_code=error.status_code, detail=error.message) from error

        return ShipWithWaybillResponse(
            ok=result.ok,
            ref=result.ref,
            package_no=result.package_no,
            tracking_no=result.tracking_no,
            shipping_provider_id=result.shipping_provider_id,
            carrier_code=result.carrier_code,
            carrier_name=result.carrier_name,
            status=result.status,
            print_data=result.print_data,
            template_url=result.template_url,
        )
