# app/pms/projections/routers/sku_codes.py
from __future__ import annotations

from fastapi import APIRouter, Query

from app.pms.projections.contracts.sku_codes import (
    PmsSkuCodesProjectionCheckOut,
    PmsSkuCodesProjectionListOut,
    PmsSkuCodesProjectionSyncOut,
)
from app.pms.projections.routers._sync import run_pms_projection_sync
from app.pms.projections.routers.deps import (
    PmsProjectionReadUserDep,
    PmsProjectionServiceDep,
    PmsProjectionWriteUserDep,
)

router = APIRouter()


@router.get("/sku-codes", response_model=PmsSkuCodesProjectionListOut)
def list_pms_sku_code_projection_rows(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
):
    return service.list_sku_codes(limit=limit, offset=offset, q=q)


@router.post("/sku-codes/sync", response_model=PmsSkuCodesProjectionSyncOut)
async def sync_pms_sku_code_projection(
    current_user: PmsProjectionWriteUserDep,
    service: PmsProjectionServiceDep,
):
    return await run_pms_projection_sync(
        lambda: service.sync_sku_codes(
            triggered_by_user_id=int(getattr(current_user, "id")),
        )
    )


@router.post("/sku-codes/check", response_model=PmsSkuCodesProjectionCheckOut)
def check_pms_sku_code_projection(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=200, ge=1, le=1000),
):
    return service.check_sku_codes(limit=limit)


__all__ = ["router"]
