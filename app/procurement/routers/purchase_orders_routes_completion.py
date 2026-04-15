# app/procurement/routers/purchase_orders_routes_completion.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.procurement.contracts.purchase_order_completion import (
    PurchaseOrderCompletionDetailOut,
    PurchaseOrderCompletionListItemOut,
)
from app.procurement.services.purchase_order_completion import PurchaseOrderCompletionService


def register(router: APIRouter, _svc: object | None = None) -> None:
    svc = PurchaseOrderCompletionService()

    @router.get("/completion", response_model=List[PurchaseOrderCompletionListItemOut])
    async def list_purchase_order_completion(
        session: AsyncSession = Depends(get_session),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        supplier_id: Optional[int] = Query(None),
        po_status: Optional[str] = Query(None),
        q: Optional[str] = Query(None),
    ) -> List[PurchaseOrderCompletionListItemOut]:
        return await svc.list_completion(
            session,
            skip=skip,
            limit=limit,
            supplier_id=supplier_id,
            po_status=po_status,
            q=q,
        )

    @router.get("/{po_id}/completion", response_model=PurchaseOrderCompletionDetailOut)
    async def get_purchase_order_completion(
        po_id: int,
        session: AsyncSession = Depends(get_session),
    ) -> PurchaseOrderCompletionDetailOut:
        try:
            return await svc.get_completion_detail(session, po_id=po_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
