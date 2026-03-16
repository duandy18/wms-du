# app/tms/config/router.py
# 分拆说明：
# - 本文件是 TMS / TransportConfig 的总路由壳；
# - 统一挂载 providers 与 warehouse_provider_bindings 两个子域；
# - URL 不变，物理归属已从旧 app/api/routers/ 收口到 app/tms/config/。
from __future__ import annotations

from fastapi import APIRouter

from app.tms.config.providers.router import router as providers_router
from app.tms.config.warehouse_provider_bindings.router import (
    router as warehouse_provider_bindings_router,
)

router = APIRouter()
router.include_router(providers_router)
router.include_router(warehouse_provider_bindings_router)
