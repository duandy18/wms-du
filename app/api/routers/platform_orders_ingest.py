# app/api/routers/platform_orders_ingest.py
from __future__ import annotations

from app.api.routers.platform_orders_ingest_routes import router
from app.api.routers.platform_orders_replay import router as replay_router
from app.api.routers.platform_orders_confirm_create import router as confirm_create_router
from app.api.routers.platform_orders_manual_decisions import router as manual_decisions_router

# ✅ 把 platform-orders 相关子路由挂进来（不改 main 注册）
router.include_router(replay_router)
router.include_router(confirm_create_router)
router.include_router(manual_decisions_router)
