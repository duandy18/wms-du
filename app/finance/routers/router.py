from __future__ import annotations

from fastapi import APIRouter

from app.finance.routers import order_sales, overview, purchase_cost, shipping_cost

router = APIRouter(prefix="/finance", tags=["finance"])


def _register_all_routes() -> None:
    overview.register(router)
    order_sales.register(router)
    purchase_cost.register(router)
    shipping_cost.register(router)


_register_all_routes()

__all__ = ["router"]
