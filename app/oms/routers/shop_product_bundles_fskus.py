# app/api/routers/shop_product_bundles_fskus.py
from __future__ import annotations

from fastapi import APIRouter

from .shop_product_bundles_fskus_routes_components import register as register_components
from .shop_product_bundles_fskus_routes_crud import register as register_crud
from .shop_product_bundles_fskus_routes_lifecycle import register as register_lifecycle


def register(router: APIRouter) -> None:
    r = APIRouter(prefix="/fskus", tags=["ops - shop-product-bundles"])

    register_crud(r)
    register_components(r)
    register_lifecycle(r)

    router.include_router(r)
