# app/wms/warehouses/routers/warehouses_routes.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.warehouses.routers import warehouses_routes_read
from app.wms.warehouses.routers import warehouses_routes_write
from app.wms.warehouses.routers import warehouses_routes_service_cities
from app.wms.warehouses.routers import warehouses_routes_service_city_split_provinces
from app.wms.warehouses.routers import warehouses_routes_service_provinces


def register(router: APIRouter) -> None:
    warehouses_routes_read.register(router)
    warehouses_routes_write.register(router)

    # 仓库服务范围（已归入 wms/warehouses 域）
    warehouses_routes_service_provinces.register(router)
    warehouses_routes_service_cities.register(router)
    warehouses_routes_service_city_split_provinces.register(router)
