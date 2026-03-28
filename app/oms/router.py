from fastapi import APIRouter

from app.oms.fsku.router import router as fsku_router
from app.oms.platforms.taobao.router_app_config import router as taobao_app_config_router
from app.oms.platforms.taobao.router_auth import router as taobao_auth_router
from app.oms.platforms.taobao.router_connection import router as taobao_connection_router
from app.oms.platforms.taobao.router_pull import router as taobao_pull_router
from app.oms.routers.platform_orders_ingest import router as platform_orders_ingest_router
from app.oms.routers.platform_shops import router as platform_shops_router
from app.oms.routers.stores import router as stores_router

router = APIRouter(prefix="/oms", tags=["OMS"])

router.include_router(platform_orders_ingest_router)
router.include_router(platform_shops_router)
router.include_router(stores_router)
router.include_router(fsku_router)
router.include_router(taobao_app_config_router)
router.include_router(taobao_auth_router)
router.include_router(taobao_connection_router)
router.include_router(taobao_pull_router)
