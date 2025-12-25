# app/api/routers/shipping_quote.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import shipping_quote_routes_calc
from app.api.routers import shipping_quote_routes_recommend
from app.api.routers.shipping_quote_schemas import (
    QuoteCalcIn,
    QuoteCalcOut,
    QuoteDestIn,
    QuoteRecommendIn,
    QuoteRecommendItemOut,
    QuoteRecommendOut,
)

router = APIRouter(tags=["shipping-quote"])


def _register_all_routes() -> None:
    shipping_quote_routes_calc.register(router)
    shipping_quote_routes_recommend.register(router)


_register_all_routes()

__all__ = [
    "router",
    "QuoteDestIn",
    "QuoteCalcIn",
    "QuoteCalcOut",
    "QuoteRecommendIn",
    "QuoteRecommendItemOut",
    "QuoteRecommendOut",
]
