# app/pms/projections/routers/uoms.py
from __future__ import annotations

from fastapi import APIRouter, Query

from app.pms.projections.contracts.uoms import (
    PmsUomsProjectionCheckOut,
    PmsUomsProjectionListOut,
    PmsUomsProjectionSyncOut,
)
from app.pms.projections.routers._sync import run_pms_projection_sync
from app.pms.projections.routers.deps import (
    PmsProjectionReadUserDep,
    PmsProjectionServiceDep,
    PmsProjectionWriteUserDep,
)

router = APIRouter()


@router.get("/uoms", response_model=PmsUomsProjectionListOut)
def list_pms_uom_projection_rows(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
):
    return service.list_uoms(limit=limit, offset=offset, q=q)


@router.post("/uoms/sync", response_model=PmsUomsProjectionSyncOut)
async def sync_pms_uom_projection(
    current_user: PmsProjectionWriteUserDep,
    service: PmsProjectionServiceDep,
):
    return await run_pms_projection_sync(
        lambda: service.sync_uoms(
            triggered_by_user_id=int(getattr(current_user, "id")),
        )
    )


@router.post("/uoms/check", response_model=PmsUomsProjectionCheckOut)
def check_pms_uom_projection(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=200, ge=1, le=1000),
):
    return service.check_uoms(limit=limit)


__all__ = ["router"]
