# app/wms/system/write_v1/routers/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.system.write_v1.routers.iam import router as iam_router
from app.wms.system.write_v1.routers.service_permissions import (
    router as service_permissions_router,
)

router = APIRouter()
router.include_router(service_permissions_router)
router.include_router(iam_router)

__all__ = ["router"]
