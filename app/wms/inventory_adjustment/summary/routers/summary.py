from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session
from app.wms.inventory_adjustment.summary.contracts.summary import (
    InventoryAdjustmentSummaryDetailOut,
    InventoryAdjustmentSummaryListOut,
    InventoryAdjustmentSummaryType,
)
from app.wms.inventory_adjustment.summary.services.summary_service import (
    get_inventory_adjustment_summary_detail,
    list_inventory_adjustment_summary,
)

router = APIRouter(
    prefix="/inventory-adjustment",
    tags=["inventory-adjustment-summary"],
)


@router.get("/summary", response_model=InventoryAdjustmentSummaryListOut)
async def list_inventory_adjustment_summary_endpoint(
    adjustment_type: InventoryAdjustmentSummaryType | None = Query(default=None),
    warehouse_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> InventoryAdjustmentSummaryListOut:
    return await list_inventory_adjustment_summary(
        session,
        adjustment_type=adjustment_type,
        warehouse_id=warehouse_id,
        limit=int(limit),
        offset=int(offset),
    )



@router.get("/summary/{adjustment_type}/{object_id}", response_model=InventoryAdjustmentSummaryDetailOut)
async def get_inventory_adjustment_summary_detail_endpoint(
    adjustment_type: InventoryAdjustmentSummaryType,
    object_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> InventoryAdjustmentSummaryDetailOut:
    try:
        return await get_inventory_adjustment_summary_detail(
            session,
            adjustment_type=adjustment_type,
            object_id=int(object_id),
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


__all__ = ["router"]
