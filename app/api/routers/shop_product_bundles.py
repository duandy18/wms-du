# app/api/routers/shop_product_bundles.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.shop_product_bundles_fskus import register as register_fskus

router = APIRouter(tags=["ops - shop-product-bundles"])

register_fskus(router)

__all__ = ["router"]
