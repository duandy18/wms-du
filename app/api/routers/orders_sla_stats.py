# app/api/routers/orders_sla_stats.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import orders_sla_stats_routes
from app.api.routers.orders_sla_stats_helpers import normalize_window as _normalize_window
from app.api.routers.orders_sla_stats_schemas import OrdersSlaStatsModel

router = APIRouter(
    prefix="/orders/stats",
    tags=["orders-sla"],
)


def _register_all_routes() -> None:
    orders_sla_stats_routes.register(router)


_register_all_routes()

__all__ = [
    "router",
    "OrdersSlaStatsModel",
    "_normalize_window",
]
