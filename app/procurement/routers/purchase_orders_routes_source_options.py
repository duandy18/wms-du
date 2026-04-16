# app/procurement/routers/purchase_orders_routes_source_options.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.procurement.contracts.purchase_order_source_options import (
    PurchaseOrderSourceOptionOut,
    PurchaseOrderSourceOptionsOut,
)
from app.procurement.repos.purchase_order_source_options_repo import (
    list_purchase_order_source_options,
)


def register(router: APIRouter, _svc: object | None = None) -> None:
    @router.get("/source-options", response_model=PurchaseOrderSourceOptionsOut)
    async def get_purchase_order_source_options(
        session: AsyncSession = Depends(get_session),
        warehouse_id: int | None = Query(None, ge=1),
        q: str | None = Query(None),
        limit: int = Query(20, ge=1, le=50),
    ) -> PurchaseOrderSourceOptionsOut:
        rows = await list_purchase_order_source_options(
            session,
            warehouse_id=warehouse_id,
            q=q,
            limit=limit,
        )
        return PurchaseOrderSourceOptionsOut(
            items=[
                PurchaseOrderSourceOptionOut(
                    po_id=int(r["po_id"]),
                    po_no=str(r["po_no"]),
                    warehouse_id=int(r["warehouse_id"]),
                    supplier_id=int(r["supplier_id"]),
                    supplier_name=str(r["supplier_name"]),
                    purchase_time=r["purchase_time"],
                    po_status=str(r["po_status"]),
                    completion_status=str(r["completion_status"]),
                    last_received_at=r.get("last_received_at"),
                )
                for r in rows
            ]
        )
