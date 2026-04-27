# Module split: platform order ingestion owns platform app config, store auth, connection checks, native pull/ingest, and native order ledgers.
from fastapi import APIRouter

from app.platform_order_ingestion.router_pull_jobs import router as platform_order_pull_jobs_router
from app.platform_order_ingestion.router_status import router as platform_order_status_router

from app.platform_order_ingestion.jd.router_app_config import router as jd_app_config_router
from app.platform_order_ingestion.jd.router_auth import router as jd_auth_router
from app.platform_order_ingestion.jd.router_connection import router as jd_connection_router
from app.platform_order_ingestion.jd.router_ingest import router as jd_ingest_router
from app.platform_order_ingestion.jd.router_orders import router as jd_orders_router
from app.platform_order_ingestion.jd.router_pull import router as jd_pull_router
from app.platform_order_ingestion.pdd.router_app_config import router as pdd_app_config_router
from app.platform_order_ingestion.pdd.router_auth import router as pdd_auth_router
from app.platform_order_ingestion.pdd.router_connection import router as pdd_connection_router
from app.platform_order_ingestion.pdd.router_ingest import router as pdd_ingest_router
from app.platform_order_ingestion.pdd.router_mock import router as pdd_mock_router
from app.platform_order_ingestion.pdd.router_orders import router as pdd_orders_router
from app.platform_order_ingestion.pdd.router_pull import router as pdd_pull_router
from app.platform_order_ingestion.taobao.router_app_config import router as taobao_app_config_router
from app.platform_order_ingestion.taobao.router_auth import router as taobao_auth_router
from app.platform_order_ingestion.taobao.router_connection import router as taobao_connection_router
from app.platform_order_ingestion.taobao.router_ingest import router as taobao_ingest_router
from app.platform_order_ingestion.taobao.router_orders import router as taobao_orders_router
from app.platform_order_ingestion.taobao.router_pull import router as taobao_pull_router

router = APIRouter(tags=["platform-order-ingestion"])

router.include_router(platform_order_pull_jobs_router)
router.include_router(platform_order_status_router)

router.include_router(taobao_app_config_router)
router.include_router(taobao_auth_router)
router.include_router(taobao_connection_router)
router.include_router(taobao_pull_router)
router.include_router(taobao_ingest_router)
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
router.include_router(jd_ingest_router)
router.include_router(jd_orders_router)
