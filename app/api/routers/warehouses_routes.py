# app/api/routers/warehouses_routes.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import warehouses_routes_read
from app.api.routers import warehouses_routes_write
from app.api.routers import warehouses_service_provinces_routes
from app.api.routers import warehouses_service_cities_routes
from app.api.routers import warehouses_service_city_split_provinces_routes
from app.api.routers import warehouses_shipping_providers_routes


def register(router: APIRouter) -> None:
    warehouses_routes_read.register(router)
    warehouses_routes_write.register(router)

    # 仓库服务范围（既有事实）
    warehouses_service_provinces_routes.register(router)
    warehouses_service_cities_routes.register(router)
    warehouses_service_city_split_provinces_routes.register(router)

    # ✅ Phase 1：仓库 × 快递公司（能力集合 / 事实绑定）
    warehouses_shipping_providers_routes.register(router)
