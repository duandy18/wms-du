from fastapi import APIRouter

from app.oms.fsku.router import router as fsku_router
from app.oms.platforms.jd.router_app_config import router as jd_app_config_router
from app.oms.platforms.jd.router_auth import router as jd_auth_router
from app.oms.platforms.jd.router_connection import router as jd_connection_router
from app.oms.platforms.jd.router_orders import router as jd_orders_router
from app.oms.platforms.jd.router_pull import router as jd_pull_router
from app.oms.platforms.pdd.router_app_config import router as pdd_app_config_router
from app.oms.platforms.pdd.router_auth import router as pdd_auth_router
from app.oms.platforms.pdd.router_connection import router as pdd_connection_router
from app.oms.platforms.pdd.router_ingest import router as pdd_ingest_router
from app.oms.platforms.pdd.router_pull import router as pdd_pull_router
from app.oms.platforms.pdd.router_orders import router as pdd_orders_router
from app.oms.platforms.pdd.router_mock import router as pdd_mock_router
from app.oms.platforms.taobao.router_app_config import router as taobao_app_config_router
from app.oms.platforms.taobao.router_auth import router as taobao_auth_router
from app.oms.platforms.taobao.router_connection import router as taobao_connection_router
from app.oms.platforms.taobao.router_pull import router as taobao_pull_router
from app.oms.platforms.taobao.router_orders import router as taobao_orders_router
from app.oms.routers.platform_orders_confirm_create import router as platform_orders_confirm_create_router
from app.oms.routers.platform_orders_ingest_routes import router as platform_orders_ingest_router
from app.oms.routers.platform_orders_manual_decisions import router as platform_orders_manual_decisions_router
from app.oms.routers.platform_orders_replay import router as platform_orders_replay_router
from app.oms.routers.stores import router as stores_router
from app.oms.orders.routers.order_outbound_options import router as order_outbound_options_router
from app.oms.orders.routers.order_outbound_view import router as order_outbound_view_router

router = APIRouter(prefix="/oms", tags=["OMS"])

router.include_router(platform_orders_ingest_router)
router.include_router(platform_orders_confirm_create_router)
router.include_router(platform_orders_replay_router)
router.include_router(platform_orders_manual_decisions_router)
router.include_router(stores_router)
router.include_router(fsku_router)
router.include_router(order_outbound_options_router)
router.include_router(order_outbound_view_router)

router.include_router(taobao_app_config_router)
router.include_router(taobao_auth_router)
router.include_router(taobao_connection_router)
router.include_router(taobao_pull_router)
router.include_router(taobao_orders_router)

router.include_router(pdd_app_config_router)
router.include_router(pdd_auth_router)
router.include_router(pdd_connection_router)
router.include_router(pdd_pull_router)
router.include_router(pdd_ingest_router)
router.include_router(pdd_orders_router)
router.include_router(pdd_mock_router)

router.include_router(jd_app_config_router)
router.include_router(jd_auth_router)
router.include_router(jd_connection_router)
router.include_router(jd_pull_router)
router.include_router(jd_orders_router)
