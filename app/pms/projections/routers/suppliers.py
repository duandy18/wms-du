# app/pms/projections/routers/suppliers.py
from __future__ import annotations

from fastapi import APIRouter, Query

from app.pms.projections.contracts.suppliers import (
    PmsSuppliersProjectionCheckOut,
    PmsSuppliersProjectionListOut,
    PmsSuppliersProjectionSyncOut,
)
from app.pms.projections.routers._sync import run_pms_projection_sync
from app.pms.projections.routers.deps import (
    PmsProjectionReadUserDep,
    PmsProjectionServiceDep,
    PmsProjectionWriteUserDep,
)

router = APIRouter()


@router.get("/suppliers", response_model=PmsSuppliersProjectionListOut)
def list_pms_supplier_projection_rows(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
):
    return service.list_suppliers(limit=limit, offset=offset, q=q)


@router.post("/suppliers/sync", response_model=PmsSuppliersProjectionSyncOut)
async def sync_pms_supplier_projection(
    current_user: PmsProjectionWriteUserDep,
    service: PmsProjectionServiceDep,
):
    return await run_pms_projection_sync(
        lambda: service.sync_suppliers(
            triggered_by_user_id=int(getattr(current_user, "id")),
        )
    )


@router.post("/suppliers/check", response_model=PmsSuppliersProjectionCheckOut)
def check_pms_supplier_projection(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=200, ge=1, le=1000),
):
    return service.check_suppliers(limit=limit)


__all__ = ["router"]
