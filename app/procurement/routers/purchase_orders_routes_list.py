# app/wms/procurement/routers/purchase_orders_routes_list.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.contracts.purchase_order import PurchaseOrderLineListOut, PurchaseOrderListItemOut
from app.procurement.services.purchase_order_line_mapper import build_line_base_data
from app.procurement.services.purchase_order_service import PurchaseOrderService


def register(router: APIRouter, _svc: PurchaseOrderService) -> None:
    @router.get("/", response_model=List[PurchaseOrderListItemOut])
    async def list_purchase_orders(
        session: AsyncSession = Depends(get_session),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        supplier: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
    ) -> List[PurchaseOrderListItemOut]:
        stmt = (
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.lines))
            .order_by(PurchaseOrder.id.desc())
            .offset(max(skip, 0))
            .limit(max(limit, 1))
        )

        if supplier:
            stmt = stmt.where(PurchaseOrder.supplier_name.ilike(f"%{supplier.strip()}%"))
        if status:
            stmt = stmt.where(PurchaseOrder.status == status.strip().upper())

        res = await session.execute(stmt)
        rows = list(res.scalars())

        out: List[PurchaseOrderListItemOut] = []

        for po in rows:
            if po.lines:
                po.lines.sort(key=lambda line: (line.line_no, line.id))

            line_out: List[PurchaseOrderLineListOut] = []

            for ln in po.lines or []:
                data = build_line_base_data(ln=ln)
                line_out.append(
                    PurchaseOrderLineListOut.model_validate(data)
                )

            out.append(
                PurchaseOrderListItemOut(
                    id=int(getattr(po, "id")),
                    po_no=str(getattr(po, "po_no") or ""),
                    warehouse_id=int(getattr(po, "warehouse_id")),
                    supplier_id=int(getattr(po, "supplier_id")),
                    supplier_name=str(getattr(po, "supplier_name") or ""),
                    total_amount=getattr(po, "total_amount", None),
                    purchaser=str(getattr(po, "purchaser") or ""),
                    purchase_time=getattr(po, "purchase_time"),
                    remark=getattr(po, "remark", None),
                    status=str(getattr(po, "status") or ""),
                    created_at=getattr(po, "created_at"),
                    updated_at=getattr(po, "updated_at"),
                    last_received_at=getattr(po, "last_received_at", None),
                    closed_at=getattr(po, "closed_at", None),
                    close_reason=getattr(po, "close_reason", None),
                    close_note=getattr(po, "close_note", None),
                    closed_by=getattr(po, "closed_by", None),
                    canceled_at=getattr(po, "canceled_at", None),
                    canceled_reason=getattr(po, "canceled_reason", None),
                    canceled_by=getattr(po, "canceled_by", None),
                    lines=line_out,
                )
            )

        return out
