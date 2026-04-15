# app/procurement/routers/purchase_reports_routes_item_lines.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.procurement.contracts.purchase_report import ItemPurchaseReportLineItem
from app.procurement.helpers.purchase_reports import apply_common_filters, time_mode_query
from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.models.purchase_order_line_completion import PurchaseOrderLineCompletion


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
        time_mode: str = time_mode_query("purchase_time"),
    ) -> List[ItemPurchaseReportLineItem]:
        stmt = (
            select(
                PurchaseOrderLineCompletion.po_id.label("po_id"),
                PurchaseOrderLineCompletion.po_no.label("po_no"),
                PurchaseOrderLineCompletion.po_line_id.label("po_line_id"),
                PurchaseOrderLineCompletion.line_no.label("line_no"),
                PurchaseOrderLineCompletion.warehouse_id.label("warehouse_id"),
                PurchaseOrderLineCompletion.supplier_id.label("supplier_id"),
                PurchaseOrderLineCompletion.supplier_name.label("supplier_name"),
                PurchaseOrderLineCompletion.purchase_time.label("purchase_time"),
                PurchaseOrderLineCompletion.purchase_uom_name_snapshot.label(
                    "purchase_uom_name_snapshot"
                ),
                PurchaseOrderLineCompletion.qty_ordered_input.label("qty_ordered_input"),
                PurchaseOrderLineCompletion.qty_ordered_base.label("qty_ordered_base"),
                PurchaseOrderLineCompletion.supply_price_snapshot.label("supply_price_snapshot"),
                PurchaseOrderLineCompletion.discount_amount_snapshot.label(
                    "discount_amount_snapshot"
                ),
                PurchaseOrderLineCompletion.planned_line_amount.label("planned_line_amount"),
                PurchaseOrderLineCompletion.line_completion_status.label("line_completion_status"),
                PurchaseOrderLineCompletion.last_received_at.label("last_received_at"),
            )
            .select_from(PurchaseOrderLineCompletion)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLineCompletion.po_id)
            .where(PurchaseOrderLineCompletion.item_id == int(item_id))
        )

        stmt = apply_common_filters(
            stmt,
            date_from=date_from,
            date_to=date_to,
            warehouse_id=warehouse_id,
            supplier_id=supplier_id,
            status=status,
            time_mode=time_mode,
        )

        stmt = stmt.order_by(
            PurchaseOrderLineCompletion.purchase_time.desc(),
            PurchaseOrderLineCompletion.po_id.desc(),
            PurchaseOrderLineCompletion.line_no.asc(),
            PurchaseOrderLineCompletion.po_line_id.asc(),
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
                    discount_amount_snapshot=Decimal(str(r["discount_amount_snapshot"] or 0)),
                    planned_line_amount=Decimal(str(r["planned_line_amount"] or 0)),
                    line_completion_status=str(r["line_completion_status"]),
                    last_received_at=r["last_received_at"],
                )
            )

        return out
