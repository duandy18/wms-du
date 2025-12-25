# app/api/routers/devconsole_orders.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import devconsole_orders_routes_demo
from app.api.routers import devconsole_orders_routes_reconcile
from app.api.routers import devconsole_orders_routes_views

# ⭐ router 必须在最上方定义
router = APIRouter(
    prefix="/dev/orders",
    tags=["devconsole-orders"],
)


def _register_all_routes() -> None:
    devconsole_orders_routes_demo.register(router)
    devconsole_orders_routes_views.register(router)
    devconsole_orders_routes_reconcile.register(router)


_register_all_routes()
