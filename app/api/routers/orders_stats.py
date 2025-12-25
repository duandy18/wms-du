# app/api/routers/orders_stats.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import orders_stats_routes
from app.api.routers.orders_stats_helpers import calc_daily_stats as _calc_daily_stats
from app.api.routers.orders_stats_schemas import (
    OrdersDailyStatsModel,
    OrdersDailyTrendItem,
    OrdersTrendResponseModel,
)

router = APIRouter(
    prefix="/orders/stats",
    tags=["orders-stats"],
)


def _register_all_routes() -> None:
    orders_stats_routes.register(router)


_register_all_routes()

__all__ = [
    "router",
    "OrdersDailyStatsModel",
    "OrdersDailyTrendItem",
    "OrdersTrendResponseModel",
    "_calc_daily_stats",
]
