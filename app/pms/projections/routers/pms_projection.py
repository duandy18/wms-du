# app/pms/projections/routers/pms_projection.py
from __future__ import annotations

from fastapi import APIRouter, Query

from app.pms.projections.contracts.pms_projection import (
    PmsProjectionStatusOut,
    PmsProjectionSyncRunsOut,
    ProjectionResource,
)
from app.pms.projections.routers import (
    barcodes,
    items,
    sku_codes,
    suppliers,
    uoms,
)
from app.pms.projections.routers.deps import (
    PmsProjectionReadUserDep,
    PmsProjectionServiceDep,
)

router = APIRouter(prefix="/projections", tags=["pms-projections"])


@router.get("/status", response_model=PmsProjectionStatusOut)
def get_pms_projection_sync_status(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
):
    return service.get_status()


@router.get("/sync-runs", response_model=PmsProjectionSyncRunsOut)
def list_pms_projection_sync_runs(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    resource: ProjectionResource | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    return service.list_sync_runs(resource=resource, limit=limit)


router.include_router(items.router)
router.include_router(suppliers.router)
router.include_router(uoms.router)
router.include_router(sku_codes.router)
router.include_router(barcodes.router)

__all__ = ["router"]
