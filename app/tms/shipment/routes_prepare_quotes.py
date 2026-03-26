# app/tms/shipment/routes_prepare_quotes.py
# 分拆说明：
# - 本文件从 routes_prepare.py 中拆出“发运准备-包裹报价”相关路由。
# - 当前只负责：
#   1) 某包裹候选报价
#   2) 某包裹确认报价
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session

from .contracts_prepare_quotes import (
    ShipPreparePackageQuoteConfirmRequest,
    ShipPreparePackageQuoteConfirmResponse,
    ShipPreparePackageQuoteResponse,
)
from .service_prepare_quotes import ShipmentPrepareQuotesService


def register(router: APIRouter) -> None:
    @router.post(
        "/ship/prepare/orders/{platform}/{shop_id}/{ext_order_no}/packages/{package_no}/quote",
        response_model=ShipPreparePackageQuoteResponse,
    )
    async def quote_prepare_package(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        package_no: int,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPreparePackageQuoteResponse:
        _ = current_user
        svc = ShipmentPrepareQuotesService(session)
        item = await svc.quote_prepare_package(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            package_no=package_no,
        )
        return ShipPreparePackageQuoteResponse(ok=True, item=item)

    @router.post(
        "/ship/prepare/orders/{platform}/{shop_id}/{ext_order_no}/packages/{package_no}/quote/confirm",
        response_model=ShipPreparePackageQuoteConfirmResponse,
    )
    async def confirm_prepare_package_quote(
        platform: str,
        shop_id: str,
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
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            package_no=package_no,
            provider_id=payload.provider_id,
        )
        return ShipPreparePackageQuoteConfirmResponse(ok=True, item=item)
