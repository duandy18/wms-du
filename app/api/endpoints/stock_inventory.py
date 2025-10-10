# app/api/endpoints/stock_inventory.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.stock import InventoryReconcileIn, InventoryReconcileOut
from app.services.stock_service import StockService

router = APIRouter(prefix="/stock/inventory", tags=["stock"])


@router.post("/reconcile", response_model=InventoryReconcileOut)
async def inventory_reconcile(
    body: InventoryReconcileIn,
    session: AsyncSession = Depends(get_session),
) -> InventoryReconcileOut:
    svc = StockService()
    res = await svc.reconcile_inventory(
        session=session,
        item_id=body.item_id,
        location_id=body.location_id,
        counted_qty=body.counted_qty,
        apply=body.apply,
        ref=body.ref,
    )
    return InventoryReconcileOut(**res)
