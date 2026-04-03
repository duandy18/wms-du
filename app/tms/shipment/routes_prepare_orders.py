# app/tms/shipment/routes_prepare_orders.py
# 分拆说明：
# - 本文件从 routes_prepare.py 中拆出“发运准备-订单与地址”相关路由。
# - 当前只负责：
#   1) 发运准备订单列表
#   2) 单订单详情
#   3) 发运准备导入
#   4) 地址核对确认
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session

from .contracts_prepare_orders import (
    ShipPrepareAddressConfirmRequest,
    ShipPrepareAddressConfirmResponse,
    ShipPrepareImportRequest,
    ShipPrepareImportResponse,
    ShipPrepareOrderDetailResponse,
    ShipPrepareOrdersListResponse,
)
from .service_prepare_orders import ShipmentPrepareOrdersService


def register(router: APIRouter) -> None:
    @router.get(
        "/ship/prepare/orders",
        response_model=ShipPrepareOrdersListResponse,
    )
    async def list_prepare_orders(
        limit: int = Query(50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPrepareOrdersListResponse:
        _ = current_user
        svc = ShipmentPrepareOrdersService(session)
        items = await svc.list_prepare_orders(limit=limit)
        return ShipPrepareOrdersListResponse(ok=True, items=items)

    @router.get(
        "/ship/prepare/orders/{platform}/{shop_id}/{ext_order_no}",
        response_model=ShipPrepareOrderDetailResponse,
    )
    async def get_prepare_order_detail(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPrepareOrderDetailResponse:
        _ = current_user
        svc = ShipmentPrepareOrdersService(session)
        item = await svc.get_prepare_order_detail(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )
        return ShipPrepareOrderDetailResponse(ok=True, item=item)

    @router.post(
        "/ship/prepare/orders/import",
        response_model=ShipPrepareImportResponse,
    )
    async def import_prepare_order(
        payload: ShipPrepareImportRequest,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPrepareImportResponse:
        _ = current_user
        svc = ShipmentPrepareOrdersService(session)
        return await svc.import_order_to_prepare(
            platform=payload.platform,
            shop_id=payload.shop_id,
            ext_order_no=payload.ext_order_no,
            address_ready_status=payload.address_ready_status,
        )

    @router.post(
        "/ship/prepare/orders/{platform}/{shop_id}/{ext_order_no}/address-confirm",
        response_model=ShipPrepareAddressConfirmResponse,
    )
    async def confirm_prepare_order_address(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        payload: ShipPrepareAddressConfirmRequest,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPrepareAddressConfirmResponse:
        _ = current_user
        svc = ShipmentPrepareOrdersService(session)
        item = await svc.confirm_order_address_ready(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            address_ready_status=payload.address_ready_status,
        )
        return ShipPrepareAddressConfirmResponse(ok=True, item=item)
