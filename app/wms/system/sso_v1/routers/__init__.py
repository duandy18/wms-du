# app/wms/system/sso_v1/routers/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.system.sso_v1.routers.exchange import router as exchange_router

router = APIRouter()
router.include_router(exchange_router)

__all__ = ["router"]
