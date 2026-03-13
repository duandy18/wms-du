# app/api/routers/shipping_records_routes_status.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.shipping_records_schemas import ShippingStatusUpdateIn, ShippingStatusUpdateOut
from app.tms.shipment import (
    ShipmentApplicationError,
    TransportShipmentService,
    UpdateShipmentStatusCommand,
)


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-records/{record_id}/status",
        response_model=ShippingStatusUpdateOut,
        summary="同步更新单条 Shipment projection / 主实体状态",
        status_code=status.HTTP_200_OK,
    )
    async def update_shipping_record_status(
        record_id: int,
        payload: ShippingStatusUpdateIn,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShippingStatusUpdateOut:
        del current_user

        shipment_svc = TransportShipmentService(session)
        command = UpdateShipmentStatusCommand(
            record_id=int(record_id),
            status=payload.status,
            delivery_time=payload.delivery_time,
            error_code=payload.error_code,
            error_message=payload.error_message,
            meta=dict(payload.meta or {}),
        )

        try:
            result = await shipment_svc.update_shipment_status(command)
        except ShipmentApplicationError as error:
            raise HTTPException(status_code=error.status_code, detail=error.message) from error

        return ShippingStatusUpdateOut(
            ok=result.ok,
            id=result.id,
            status=result.status,
            delivery_time=result.delivery_time,
        )
