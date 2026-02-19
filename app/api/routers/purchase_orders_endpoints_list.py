# app/api/routers/purchase_orders_endpoints_list.py
"""
Purchase Orders Endpoints - List（列表读模型）
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.purchase_order import PurchaseOrder
from app.models.warehouse import Warehouse
from app.schemas.purchase_order import PurchaseOrderLineListOut, PurchaseOrderListItemOut
from app.services.qty_base import ordered_base as _ordered_base_impl
from app.services.qty_base import received_base as _received_base_impl
from app.services.purchase_order_service import PurchaseOrderService


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
            stmt = stmt.where(PurchaseOrder.supplier.ilike(f"%{supplier.strip()}%"))
        if status:
            stmt = stmt.where(PurchaseOrder.status == status.strip().upper())

        res = await session.execute(stmt)
        rows = list(res.scalars())

        wh_ids = sorted({int(getattr(po, "warehouse_id")) for po in rows if getattr(po, "warehouse_id", None) is not None})
        wh_map: dict[int, str] = {}
        if wh_ids:
            wh_rows = (await session.execute(select(Warehouse.id, Warehouse.name).where(Warehouse.id.in_(wh_ids)))).all()
            for wid, name in wh_rows:
                if wid is None:
                    continue
                wh_map[int(wid)] = str(name or "")

        out: List[PurchaseOrderListItemOut] = []
        for po in rows:
            if po.lines:
                po.lines.sort(key=lambda line: (line.line_no, line.id))

            line_out: List[PurchaseOrderLineListOut] = []
            for ln in (po.lines or []):
                ordered_base = int(_ordered_base_impl(ln) or 0)
                received_base = int(_received_base_impl(ln) or 0)

                line_out.append(
                    PurchaseOrderLineListOut(
                        id=int(getattr(ln, "id")),
                        po_id=int(getattr(ln, "po_id")),
                        line_no=int(getattr(ln, "line_no")),
                        item_id=int(getattr(ln, "item_id")),
                        qty_ordered=int(getattr(ln, "qty_ordered") or 0),
                        qty_ordered_base=ordered_base,
                        qty_received_base=received_base,
                        status=str(getattr(ln, "status") or ""),
                        units_per_case=getattr(ln, "units_per_case", None),
                        base_uom=getattr(ln, "base_uom", None),
                        purchase_uom=getattr(ln, "purchase_uom", None),
                        created_at=getattr(ln, "created_at"),
                        updated_at=getattr(ln, "updated_at"),
                    )
                )

            wid = int(getattr(po, "warehouse_id"))
            out.append(
                PurchaseOrderListItemOut(
                    id=int(getattr(po, "id")),
                    supplier=str(getattr(po, "supplier") or ""),
                    warehouse_id=wid,
                    warehouse_name=wh_map.get(wid) or None,
                    supplier_id=getattr(po, "supplier_id", None),
                    supplier_name=getattr(po, "supplier_name", None),
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
