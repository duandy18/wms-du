from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session
from app.oms.order_facts.contracts.fulfillment_conversion import (
    FulfillmentOrderConversionIn,
    FulfillmentOrderConversionOut,
)
from app.oms.order_facts.services.fulfillment_conversion_service import (
    FulfillmentConversionNotFound,
    FulfillmentConversionValidationError,
    convert_platform_order_mirror_to_fulfillment_order,
)


router = APIRouter(tags=["oms-fulfillment-order-conversion"])


def _route_name(platform: str, suffix: str) -> str:
    return f"{platform}_{suffix}"


def _register_platform_routes(platform: str) -> None:
    @router.post(
        f"/{platform}/fulfillment-order-conversion/convert",
        response_model=FulfillmentOrderConversionOut,
        name=_route_name(platform, "convert_platform_fulfillment_order"),
    )
    async def convert_platform_fulfillment_order(
        payload: FulfillmentOrderConversionIn = Body(...),
        session: AsyncSession = Depends(get_async_session),
    ) -> FulfillmentOrderConversionOut:
        try:
            return await convert_platform_order_mirror_to_fulfillment_order(
                session,
                platform=platform,
                mirror_id=int(payload.mirror_id),
            )
        except FulfillmentConversionNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FulfillmentConversionValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


for _platform in ("pdd", "taobao", "jd"):
    _register_platform_routes(_platform)
