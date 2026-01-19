# app/api/routers/warehouses_routes.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import warehouses_routes_read
from app.api.routers import warehouses_routes_write
from app.api.routers import warehouses_service_provinces_routes
from app.api.routers import warehouses_service_cities_routes
from app.api.routers import warehouses_service_city_split_provinces_routes


def register(router: APIRouter) -> None:
    warehouses_routes_read.register(router)
    warehouses_routes_write.register(router)
    warehouses_service_provinces_routes.register(router)
    warehouses_service_cities_routes.register(router)
    warehouses_service_city_split_provinces_routes.register(router)
