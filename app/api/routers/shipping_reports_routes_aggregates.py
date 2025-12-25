# app/api/routers/shipping_reports_routes_aggregates.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import shipping_reports_routes_by_carrier
from app.api.routers import shipping_reports_routes_by_province
from app.api.routers import shipping_reports_routes_by_shop
from app.api.routers import shipping_reports_routes_by_warehouse
from app.api.routers import shipping_reports_routes_daily


def register(router: APIRouter) -> None:
    shipping_reports_routes_by_carrier.register(router)
    shipping_reports_routes_by_province.register(router)
    shipping_reports_routes_by_shop.register(router)
    shipping_reports_routes_by_warehouse.register(router)
    shipping_reports_routes_daily.register(router)
