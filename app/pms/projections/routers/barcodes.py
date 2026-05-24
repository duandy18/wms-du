# app/pms/projections/routers/barcodes.py
from __future__ import annotations

from fastapi import APIRouter, Query

from app.pms.projections.contracts.barcodes import (
    PmsBarcodesProjectionCheckOut,
    PmsBarcodesProjectionListOut,
    PmsBarcodesProjectionSyncOut,
)
from app.pms.projections.routers._sync import run_pms_projection_sync
from app.pms.projections.routers.deps import (
    PmsProjectionReadUserDep,
    PmsProjectionServiceDep,
    PmsProjectionWriteUserDep,
)

router = APIRouter()


@router.get("/barcodes", response_model=PmsBarcodesProjectionListOut)
def list_pms_barcode_projection_rows(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
):
    return service.list_barcodes(limit=limit, offset=offset, q=q)


@router.post("/barcodes/sync", response_model=PmsBarcodesProjectionSyncOut)
async def sync_pms_barcode_projection(
    current_user: PmsProjectionWriteUserDep,
    service: PmsProjectionServiceDep,
):
    return await run_pms_projection_sync(
        lambda: service.sync_barcodes(
            triggered_by_user_id=int(getattr(current_user, "id")),
        )
    )


@router.post("/barcodes/check", response_model=PmsBarcodesProjectionCheckOut)
def check_pms_barcode_projection(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=200, ge=1, le=1000),
):
    return service.check_barcodes(limit=limit)


__all__ = ["router"]
