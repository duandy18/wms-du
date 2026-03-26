# app/tms/shipment/routes_prepare_packages.py
# 分拆说明：
# - 本文件从 routes_prepare.py 中拆出“发运准备-包裹基础事实”相关路由。
# - 当前只负责：
#   1) 包裹列表
#   2) 新增包裹
#   3) 更新包裹基础信息（重量 / 发货仓）
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session

from .contracts_prepare_packages import (
    ShipPreparePackageCreateResponse,
    ShipPreparePackagesResponse,
    ShipPreparePackageUpdateRequest,
    ShipPreparePackageUpdateResponse,
)
from .service_prepare_packages import ShipmentPreparePackagesService


def register(router: APIRouter) -> None:
    @router.get(
        "/ship/prepare/orders/{platform}/{shop_id}/{ext_order_no}/packages",
        response_model=ShipPreparePackagesResponse,
    )
    async def list_prepare_packages(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPreparePackagesResponse:
        _ = current_user
        svc = ShipmentPreparePackagesService(session)
        items = await svc.list_prepare_packages(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )
        return ShipPreparePackagesResponse(ok=True, items=items)

    @router.post(
        "/ship/prepare/orders/{platform}/{shop_id}/{ext_order_no}/packages",
        response_model=ShipPreparePackageCreateResponse,
    )
    async def create_prepare_package(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPreparePackageCreateResponse:
        _ = current_user
        svc = ShipmentPreparePackagesService(session)
        item = await svc.create_prepare_package(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
        )
        return ShipPreparePackageCreateResponse(ok=True, item=item)

    @router.patch(
        "/ship/prepare/orders/{platform}/{shop_id}/{ext_order_no}/packages/{package_no}",
        response_model=ShipPreparePackageUpdateResponse,
    )
    async def update_prepare_package(
        platform: str,
        shop_id: str,
        ext_order_no: str,
        package_no: int,
        payload: ShipPreparePackageUpdateRequest,
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
    ) -> ShipPreparePackageUpdateResponse:
        _ = current_user
        svc = ShipmentPreparePackagesService(session)
        item = await svc.update_prepare_package(
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            package_no=package_no,
            weight_kg=payload.weight_kg,
            warehouse_id=payload.warehouse_id,
        )
        return ShipPreparePackageUpdateResponse(ok=True, item=item)
