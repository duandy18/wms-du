# app/shipping_assist/shipment/routes_prepare_quotes.py
# 分拆说明：
# - 本文件从 routes_prepare.py 中拆出“发运准备-包裹报价”相关路由。
# - 当前只负责：
#   1) 某包裹候选报价
#   2) 某包裹确认报价
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session

from .contracts_prepare_quotes import (
    ShipPreparePackageQuoteConfirmRequest,
    ShipPreparePackageQuoteConfirmResponse,
    ShipPreparePackageQuoteResponse,
)
from .service_prepare_quotes import ShipmentPrepareQuotesService


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-assist/shipping/prepare/orders/{platform}/{store_code}/{ext_order_no}/packages/{package_no}/quote",
        response_model=ShipPreparePackageQuoteResponse,
    )
    async def quote_prepare_package(
        platform: str,
        store_code: str,
        ext_order_no: str,
        package_no: int,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPreparePackageQuoteResponse:
        _ = current_user
        svc = ShipmentPrepareQuotesService(session)
        item = await svc.quote_prepare_package(
            platform=platform,
            store_code=store_code,
            ext_order_no=ext_order_no,
            package_no=package_no,
        )
        return ShipPreparePackageQuoteResponse(ok=True, item=item)

    @router.post(
        "/shipping-assist/shipping/prepare/orders/{platform}/{store_code}/{ext_order_no}/packages/{package_no}/quote/confirm",
        response_model=ShipPreparePackageQuoteConfirmResponse,
    )
    async def confirm_prepare_package_quote(
        platform: str,
        store_code: str,
        ext_order_no: str,
        package_no: int,
        payload: ShipPreparePackageQuoteConfirmRequest,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPreparePackageQuoteConfirmResponse:
        _ = current_user
        svc = ShipmentPrepareQuotesService(session)
        item = await svc.confirm_prepare_package_quote(
            platform=platform,
            store_code=store_code,
            ext_order_no=ext_order_no,
            package_no=package_no,
            provider_id=payload.provider_id,
        )
        return ShipPreparePackageQuoteConfirmResponse(ok=True, item=item)
