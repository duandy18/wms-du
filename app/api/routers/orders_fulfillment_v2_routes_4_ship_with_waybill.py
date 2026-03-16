# app/api/routers/orders_fulfillment_v2_routes_4_ship_with_waybill.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.orders_fulfillment_v2_schemas import (
    ShipWithWaybillRequest,
    ShipWithWaybillResponse,
)
from app.tms.shipment import (
    ShipmentApplicationError,
    ShipWithWaybillCommand,
    TransportShipmentService,
)
from app.tms.shipment.router_helpers import get_order_ref_and_trace_id


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
            warehouse_id=int(body.warehouse_id),
            shipping_provider_id=int(body.shipping_provider_id),
            carrier_code=body.carrier_code,
            carrier_name=body.carrier_name,
            weight_kg=float(body.weight_kg),
            receiver_name=body.receiver_name,
            receiver_phone=body.receiver_phone,
            province=body.province,
            city=body.city,
            district=body.district,
            address_detail=body.address_detail,
            quote_snapshot=body.meta.quote_snapshot.model_dump() if body.meta else {},
            meta=dict(body.meta.extra) if body.meta else {},
        )

        try:
            result = await shipment_svc.ship_with_waybill(command)
        except ShipmentApplicationError as error:
            raise HTTPException(status_code=error.status_code, detail=error.message) from error

        return ShipWithWaybillResponse(
            ok=result.ok,
            ref=result.ref,
            tracking_no=result.tracking_no,
            shipping_provider_id=result.shipping_provider_id,
            carrier_code=result.carrier_code,
            carrier_name=result.carrier_name,
            status=result.status,
            label_base64=result.label_base64,
            label_format=result.label_format,
        )
