from fastapi import APIRouter

from app.oms.routers.platform_orders_ingest import router as platform_orders_ingest_router
from app.oms.routers.platform_shops import router as platform_shops_router
from app.oms.routers.stores import router as stores_router
from app.oms.routers.shop_product_bundles import router as shop_product_bundles_router

router = APIRouter(prefix="/oms", tags=["OMS"])

router.include_router(platform_orders_ingest_router)
router.include_router(platform_shops_router)
router.include_router(stores_router)
router.include_router(shop_product_bundles_router)
