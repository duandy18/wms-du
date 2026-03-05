# app/api/routers/warehouses_shipping_providers_routes.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import warehouses_shipping_providers_routes_bindings
from app.api.routers import warehouses_shipping_providers_routes_summary


def register(router: APIRouter) -> None:
    warehouses_shipping_providers_routes_summary.register(router)
    warehouses_shipping_providers_routes_bindings.register(router)
