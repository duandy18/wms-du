# app/procurement/routers/purchase_reports_routes_suppliers.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.procurement.contracts.purchase_report import SupplierPurchaseReportItem
from app.procurement.helpers.purchase_reports import (
    apply_common_filters,
    resolve_report_item_ids,
    time_mode_query,
)
from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.models.purchase_order_line_completion import PurchaseOrderLineCompletion


def register(router: APIRouter) -> None:
    @router.get("/suppliers", response_model=List[SupplierPurchaseReportItem])
    async def purchase_report_by_suppliers(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        supplier_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        item_id: Optional[int] = Query(None),
        item_keyword: Optional[str] = Query(None),
        time_mode: str = time_mode_query("purchase_time"),
    ) -> List[SupplierPurchaseReportItem]:
        report_item_ids = await resolve_report_item_ids(
            session,
            item_id=item_id,
            item_keyword=item_keyword,
        )
        if report_item_ids is not None and not report_item_ids:
            return []

        supplier_name_expr = func.coalesce(
            PurchaseOrderLineCompletion.supplier_name,
            "",
        ).label("supplier_name")

        stmt = (
            select(
                PurchaseOrderLineCompletion.supplier_id.label("supplier_id"),
                supplier_name_expr,
                func.count(distinct(PurchaseOrderLineCompletion.po_id)).label("order_count"),
                func.coalesce(
                    func.sum(PurchaseOrderLineCompletion.qty_ordered_input),
                    0,
                ).label("total_qty_cases"),
                func.coalesce(
                    func.sum(PurchaseOrderLineCompletion.qty_ordered_base),
                    0,
                ).label("total_units"),
                func.coalesce(
                    func.sum(PurchaseOrderLineCompletion.planned_line_amount),
                    0,
                ).label("total_amount"),
            )
            .select_from(PurchaseOrderLineCompletion)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLineCompletion.po_id)
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

        if report_item_ids is not None:
            stmt = stmt.where(PurchaseOrderLineCompletion.item_id.in_(report_item_ids))

        stmt = stmt.group_by(
            PurchaseOrderLineCompletion.supplier_id,
            supplier_name_expr,
        ).order_by(supplier_name_expr.asc(), PurchaseOrderLineCompletion.supplier_id.asc())

        rows = (await session.execute(stmt)).mappings().all()
        items: List[SupplierPurchaseReportItem] = []

        for row in rows:
            total_units = int(row["total_units"] or 0)
            total_amount = Decimal(str(row["total_amount"] or 0))
            avg_unit_price = (
                (total_amount / total_units).quantize(Decimal("0.0001"))
                if total_units > 0
                else None
            )

            items.append(
                SupplierPurchaseReportItem(
                    supplier_id=int(row["supplier_id"]) if row["supplier_id"] is not None else None,
                    supplier_name=str(row["supplier_name"] or ""),
                    order_count=int(row["order_count"] or 0),
                    total_qty_cases=int(row["total_qty_cases"] or 0),
                    total_units=total_units,
                    total_amount=total_amount,
                    avg_unit_price=avg_unit_price,
                )
            )

        return items
