# app/pms/projections/routers/items.py
from __future__ import annotations

from fastapi import APIRouter, Query

from app.pms.projections.contracts.items import (
    PmsItemsProjectionCheckOut,
    PmsItemsProjectionListOut,
    PmsItemsProjectionSyncOut,
)
from app.pms.projections.routers._sync import run_pms_projection_sync
from app.pms.projections.routers.deps import (
    PmsProjectionReadUserDep,
    PmsProjectionServiceDep,
    PmsProjectionWriteUserDep,
)

router = APIRouter()


@router.get("/items", response_model=PmsItemsProjectionListOut)
def list_pms_item_projection_rows(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None),
):
    return service.list_items(limit=limit, offset=offset, q=q)


@router.post("/items/sync", response_model=PmsItemsProjectionSyncOut)
async def sync_pms_item_projection(
    current_user: PmsProjectionWriteUserDep,
    service: PmsProjectionServiceDep,
):
    return await run_pms_projection_sync(
        lambda: service.sync_items(
            triggered_by_user_id=int(getattr(current_user, "id")),
        )
    )


@router.post("/items/check", response_model=PmsItemsProjectionCheckOut)
def check_pms_item_projection(
    _: PmsProjectionReadUserDep,
    service: PmsProjectionServiceDep,
    limit: int = Query(default=200, ge=1, le=1000),
):
    return service.check_items(limit=limit)


__all__ = ["router"]
