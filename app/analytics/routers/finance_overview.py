# app/analytics/routers/finance_overview.py
from __future__ import annotations

from fastapi import APIRouter

from app.analytics.routers import finance_overview_routes_daily
from app.analytics.routers import finance_overview_routes_order_unit
from app.analytics.routers import finance_overview_routes_shop
from app.analytics.routers import finance_overview_routes_sku

router = APIRouter(prefix="/finance", tags=["finance"])


def _register_all_routes() -> None:
    finance_overview_routes_daily.register(router)
    finance_overview_routes_shop.register(router)
    finance_overview_routes_sku.register(router)
    finance_overview_routes_order_unit.register(router)


_register_all_routes()
