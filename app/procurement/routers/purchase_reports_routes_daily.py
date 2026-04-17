# app/procurement/routers/purchase_reports_routes_daily.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.procurement.contracts.purchase_report import DailyPurchaseReportItem
from app.procurement.helpers.purchase_reports import resolve_report_item_ids
from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.models.purchase_order_line import PurchaseOrderLine


def register(router: APIRouter) -> None:
    @router.get("/daily", response_model=List[DailyPurchaseReportItem])
    async def purchase_report_daily(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        supplier_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        item_id: Optional[int] = Query(None),
        item_keyword: Optional[str] = Query(None),
    ) -> List[DailyPurchaseReportItem]:
        report_item_ids = await resolve_report_item_ids(
            session,
            item_id=item_id,
            item_keyword=item_keyword,
        )
        if report_item_ids is not None and not report_item_ids:
            return []

        day_expr = func.date(PurchaseOrder.purchase_time).label("day")
        planned_line_amount_expr = (
            func.coalesce(PurchaseOrderLine.supply_price, 0)
            * PurchaseOrderLine.qty_ordered_base
            - func.coalesce(PurchaseOrderLine.discount_amount, 0)
        )

        stmt = (
            select(
                day_expr,
                func.count(distinct(PurchaseOrderLine.po_id)).label("order_count"),
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

        stmt = stmt.group_by(day_expr).order_by(day_expr)

        rows = (await session.execute(stmt)).mappings().all()
        return [
            DailyPurchaseReportItem(
                day=row["day"],
                order_count=int(row["order_count"] or 0),
                total_qty_cases=int(row["total_qty_cases"] or 0),
                total_units=int(row["total_units"] or 0),
                total_amount=Decimal(str(row["total_amount"] or 0)),
            )
            for row in rows
        ]
