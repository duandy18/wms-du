# app/procurement/routers/purchase_reports_routes_item_lines.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.procurement.contracts.purchase_report import ItemPurchaseReportLineItem
from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.models.purchase_order_line import PurchaseOrderLine


def register(router: APIRouter) -> None:
    @router.get("/items/{item_id}/lines", response_model=List[ItemPurchaseReportLineItem])
    async def purchase_report_item_lines(
        item_id: int,
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        supplier_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
    ) -> List[ItemPurchaseReportLineItem]:
        planned_line_amount_expr = (
            func.coalesce(PurchaseOrderLine.supply_price, 0)
            * PurchaseOrderLine.qty_ordered_base
        )

        stmt = (
            select(
                PurchaseOrder.id.label("po_id"),
                PurchaseOrder.po_no.label("po_no"),
                PurchaseOrderLine.id.label("po_line_id"),
                PurchaseOrderLine.line_no.label("line_no"),
                PurchaseOrder.warehouse_id.label("warehouse_id"),
                PurchaseOrder.supplier_id.label("supplier_id"),
                PurchaseOrder.supplier_name.label("supplier_name"),
                PurchaseOrder.purchase_time.label("purchase_time"),
                PurchaseOrderLine.purchase_uom_name_snapshot.label(
                    "purchase_uom_name_snapshot"
                ),
                PurchaseOrderLine.qty_ordered_input.label("qty_ordered_input"),
                PurchaseOrderLine.qty_ordered_base.label("qty_ordered_base"),
                PurchaseOrderLine.supply_price.label("supply_price_snapshot"),
                planned_line_amount_expr.label("planned_line_amount"),
            )
            .select_from(PurchaseOrderLine)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.po_id)
            .where(PurchaseOrderLine.item_id == int(item_id))
        )

        normalized_status = str(status or "").strip().upper()
        if normalized_status:
            stmt = stmt.where(PurchaseOrder.status == normalized_status)

        if date_from is not None:
            stmt = stmt.where(
                PurchaseOrder.purchase_time >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                PurchaseOrder.purchase_time <= datetime.combine(date_to, datetime.max.time())
            )
        if warehouse_id is not None:
            stmt = stmt.where(PurchaseOrder.warehouse_id == warehouse_id)
        if supplier_id is not None:
            stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)

        stmt = stmt.order_by(
            PurchaseOrder.purchase_time.desc(),
            PurchaseOrder.id.desc(),
            PurchaseOrderLine.line_no.asc(),
            PurchaseOrderLine.id.asc(),
        )

        rows = (await session.execute(stmt)).mappings().all()

        out: List[ItemPurchaseReportLineItem] = []
        for r in rows:
            out.append(
                ItemPurchaseReportLineItem(
                    po_id=int(r["po_id"]),
                    po_no=str(r["po_no"]),
                    po_line_id=int(r["po_line_id"]),
                    line_no=int(r["line_no"]),
                    warehouse_id=int(r["warehouse_id"]),
                    supplier_id=int(r["supplier_id"]),
                    supplier_name=str(r["supplier_name"]),
                    purchase_time=r["purchase_time"],
                    purchase_uom_name_snapshot=str(r["purchase_uom_name_snapshot"]),
                    qty_ordered_input=int(r["qty_ordered_input"] or 0),
                    qty_ordered_base=int(r["qty_ordered_base"] or 0),
                    supply_price_snapshot=(
                        Decimal(str(r["supply_price_snapshot"]))
                        if r["supply_price_snapshot"] is not None
                        else None
                    ),
                    planned_line_amount=Decimal(str(r["planned_line_amount"] or 0)),
                )
            )

        return out
