# app/api/routers/shop_product_bundles.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.shop_product_bundles_fskus import register as register_fskus
from app.api.routers.shop_product_bundles_platform_sku_bindings import (
    register as register_bindings,
)
from app.api.routers.shop_product_bundles_platform_skus_mirror import (
    register as register_mirror,
)

router = APIRouter(tags=["ops - shop-product-bundles"])

register_fskus(router)
register_bindings(router)
register_mirror(router)

__all__ = ["router"]
