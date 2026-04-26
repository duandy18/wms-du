# app/shipping_assist/reports/routes_aggregates.py
from __future__ import annotations

from fastapi import APIRouter

from app.shipping_assist.reports import routes_by_carrier
from app.shipping_assist.reports import routes_by_province
from app.shipping_assist.reports import routes_by_store
from app.shipping_assist.reports import routes_by_warehouse
from app.shipping_assist.reports import routes_daily


def register(router: APIRouter) -> None:
    routes_by_carrier.register(router)
    routes_by_province.register(router)
    routes_by_store.register(router)
    routes_by_warehouse.register(router)
    routes_daily.register(router)
