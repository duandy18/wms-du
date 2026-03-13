# app/api/routers/outbound_ship_routes_confirm.py
from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.outbound_ship_schemas import ShipConfirmRequest, ShipConfirmResponse
from app.services.audit_writer import AuditEventWriter
from app.tms.shipment import (
    ConfirmShipmentCommand,
    ShipmentApplicationError,
    TransportShipmentService,
)


def _raise_http_from_app_error(error: ShipmentApplicationError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )


def register(router: APIRouter) -> None:
    @router.post("/ship/confirm", response_model=ShipConfirmResponse)
    async def confirm_ship(
        payload: ShipConfirmRequest,
        session: AsyncSession = Depends(get_session),
        current_user: object = Depends(get_current_user),
    ) -> ShipConfirmResponse:
        del current_user

        platform_norm = payload.platform.upper()
        shipment_svc = TransportShipmentService(session)

        async def _audit_reject(error_code: str, message: str) -> None:
            meta: Dict[str, object] = {
                "platform": platform_norm,
                "shop_id": payload.shop_id,
                "error_code": error_code,
                "message": message,
                "provider_id": int(payload.shipping_provider_id),
            }

            if payload.trace_id:
                meta["trace_id"] = payload.trace_id

            if payload.warehouse_id is not None:
                meta["warehouse_id"] = int(payload.warehouse_id)

            if payload.scheme_id is not None:
                meta["scheme_id"] = int(payload.scheme_id)

            await AuditEventWriter.write(
                session,
                flow="OUTBOUND",
                event="SHIP_CONFIRM_REJECT",
                ref=payload.ref,
                trace_id=payload.trace_id,
                meta=meta,
                auto_commit=True,
            )

        command = ConfirmShipmentCommand(
            ref=payload.ref,
            platform=payload.platform,
            shop_id=payload.shop_id,
            trace_id=payload.trace_id,
            warehouse_id=int(payload.warehouse_id or 0),
            shipping_provider_id=int(payload.shipping_provider_id),
            scheme_id=int(payload.scheme_id or 0),
            tracking_no=payload.tracking_no,
            gross_weight_kg=payload.gross_weight_kg,
            packaging_weight_kg=payload.packaging_weight_kg,
            cost_estimated=payload.cost_estimated,
            cost_real=payload.cost_real,
            delivery_time=payload.delivery_time,
            status=payload.status,
            error_code=payload.error_code,
            error_message=payload.error_message,
            meta=dict(payload.meta or {}),
        )

        try:
            result = await shipment_svc.confirm_shipment(command)
        except ShipmentApplicationError as error:
            if error.status_code in (409, 422):
                await _audit_reject(error.code, error.message)
            _raise_http_from_app_error(error)

        return ShipConfirmResponse(
            ok=result.ok,
            ref=result.ref,
            trace_id=result.trace_id,
        )
