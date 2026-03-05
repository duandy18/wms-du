# app/api/routers/purchase_orders_endpoints_list.py
"""
Purchase Orders Endpoints - List（列表读模型）
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models.purchase_order import PurchaseOrder
from app.schemas.purchase_order import PurchaseOrderLineListOut, PurchaseOrderListItemOut
from app.services.purchase_order_line_mapper import build_line_base_data
from app.services.purchase_order_service import PurchaseOrderService


async def _load_confirmed_received_base_map(
    session: AsyncSession, *, po_line_ids: list[int]
) -> dict[int, int]:
    if not po_line_ids:
        return {}

    sql = text(
        """
        SELECT rl.po_line_id AS po_line_id,
               COALESCE(SUM(rl.qty_base), 0)::int AS qty
          FROM inbound_receipt_lines rl
          JOIN inbound_receipts r
            ON r.id = rl.receipt_id
         WHERE r.source_type = 'PO'
           AND r.status = 'CONFIRMED'
           AND rl.po_line_id = ANY(:ids)
         GROUP BY rl.po_line_id
        """
    )

    rows = (await session.execute(sql, {"ids": [int(x) for x in po_line_ids]})).mappings().all()

    out: dict[int, int] = {}
    for r in rows:
        pid = int(r.get("po_line_id") or 0)
        if pid > 0:
            out[pid] = int(r.get("qty") or 0)
    return out


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

        po_line_ids: list[int] = []
        for po in rows:
            for ln in po.lines or []:
                lid = getattr(ln, "id", None)
                if lid is not None:
                    po_line_ids.append(int(lid))

        received_map = await _load_confirmed_received_base_map(
            session, po_line_ids=po_line_ids
        )

        out: List[PurchaseOrderListItemOut] = []

        for po in rows:
            if po.lines:
                po.lines.sort(key=lambda line: (line.line_no, line.id))

            line_out: List[PurchaseOrderLineListOut] = []

            for ln in po.lines or []:
                ln_id = int(getattr(ln, "id"))
                received_base = int(received_map.get(ln_id, 0) or 0)

                data = build_line_base_data(ln=ln, received_base=received_base)

                line_out.append(
                    PurchaseOrderLineListOut.model_validate(data)
                )

            out.append(
                PurchaseOrderListItemOut(
                    id=int(getattr(po, "id")),
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
