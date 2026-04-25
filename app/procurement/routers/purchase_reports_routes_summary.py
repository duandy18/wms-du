# app/procurement/routers/purchase_reports_routes_summary.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.procurement.contracts.purchase_report import SummaryPurchaseReportItem
from app.procurement.helpers.purchase_reports import resolve_report_item_ids
from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.models.purchase_order_line import PurchaseOrderLine


def _empty_summary() -> SummaryPurchaseReportItem:
    return SummaryPurchaseReportItem(
        order_count=0,
        supplier_count=0,
        item_count=0,
        total_qty_cases=0,
        total_units=0,
        total_amount=Decimal("0"),
        avg_unit_price=None,
    )


def register(router: APIRouter) -> None:
    @router.get("/summary", response_model=SummaryPurchaseReportItem)
    async def purchase_report_summary(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        supplier_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        item_id: Optional[int] = Query(None),
        item_keyword: Optional[str] = Query(None),
    ) -> SummaryPurchaseReportItem:
        report_item_ids = await resolve_report_item_ids(
            session,
            item_id=item_id,
            item_keyword=item_keyword,
        )
        if report_item_ids is not None and not report_item_ids:
            return _empty_summary()

        planned_line_amount_expr = (
            func.coalesce(PurchaseOrderLine.supply_price, 0)
            * PurchaseOrderLine.qty_ordered_base
        )

        stmt = (
            select(
                func.count(distinct(PurchaseOrderLine.po_id)).label("order_count"),
                func.count(distinct(PurchaseOrder.supplier_id)).label("supplier_count"),
                func.count(distinct(PurchaseOrderLine.item_id)).label("item_count"),
                func.coalesce(
                    func.sum(PurchaseOrderLine.qty_ordered_input),
                    0,
                ).label("total_qty_cases"),
                func.coalesce(
                    func.sum(PurchaseOrderLine.qty_ordered_base),
                    0,
                ).label("total_units"),
                func.coalesce(
                    func.sum(planned_line_amount_expr),
                    0,
                ).label("total_amount"),
            )
            .select_from(PurchaseOrderLine)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.po_id)
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
        if report_item_ids is not None:
            stmt = stmt.where(PurchaseOrderLine.item_id.in_(report_item_ids))

        row = (await session.execute(stmt)).mappings().one()

        total_units = int(row["total_units"] or 0)
        total_amount = Decimal(str(row["total_amount"] or 0))
        avg_unit_price = (
            (total_amount / total_units).quantize(Decimal("0.0001"))
            if total_units > 0
            else None
        )

        return SummaryPurchaseReportItem(
            order_count=int(row["order_count"] or 0),
            supplier_count=int(row["supplier_count"] or 0),
            item_count=int(row["item_count"] or 0),
            total_qty_cases=int(row["total_qty_cases"] or 0),
            total_units=total_units,
            total_amount=total_amount,
            avg_unit_price=avg_unit_price,
        )
