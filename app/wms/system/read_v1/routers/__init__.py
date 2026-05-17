# app/wms/system/read_v1/routers/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.system.read_v1.routers.app_manifest import router as app_manifest_router
from app.wms.system.read_v1.routers.page_catalog import router as page_catalog_router
from app.wms.system.read_v1.routers.service_capabilities import (
    router as service_capabilities_router,
)

router = APIRouter()
router.include_router(app_manifest_router)
router.include_router(page_catalog_router)
router.include_router(service_capabilities_router)

__all__ = ["router"]
