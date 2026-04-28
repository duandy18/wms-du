from fastapi import APIRouter

from app.oms.fsku.router import router as fsku_router
from app.oms.order_facts.router import router as order_facts_router
from app.oms.routers.platform_orders_confirm_create import router as platform_orders_confirm_create_router
from app.oms.routers.platform_orders_ingest_routes import router as platform_orders_ingest_router
from app.oms.routers.platform_orders_manual_decisions import router as platform_orders_manual_decisions_router
from app.oms.routers.platform_orders_replay import router as platform_orders_replay_router
from app.oms.routers.platform_orders_resolve_preview import router as platform_orders_resolve_preview_router
from app.oms.routers.stores import router as stores_router
from app.oms.orders.routers.order_outbound_options import router as order_outbound_options_router
from app.oms.orders.routers.order_outbound_view import router as order_outbound_view_router

router = APIRouter(prefix="/oms", tags=["OMS"])
router.include_router(order_facts_router)

router.include_router(platform_orders_ingest_router)
router.include_router(platform_orders_confirm_create_router)
router.include_router(platform_orders_replay_router)
router.include_router(platform_orders_resolve_preview_router)
router.include_router(platform_orders_manual_decisions_router)
router.include_router(stores_router)
router.include_router(fsku_router)
router.include_router(order_outbound_options_router)
router.include_router(order_outbound_view_router)
