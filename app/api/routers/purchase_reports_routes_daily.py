# app/api/routers/purchase_reports_routes_daily.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.schemas.purchase_report import DailyPurchaseReportItem

from app.api.routers.purchase_reports_helpers import apply_common_filters


def register(router: APIRouter) -> None:
    @router.get("/daily", response_model=List[DailyPurchaseReportItem])
    async def purchase_report_daily(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None, description="起始日期（含），按采购单创建时间过滤"),
        date_to: Optional[date] = Query(None, description="结束日期（含），按采购单创建时间过滤"),
        warehouse_id: Optional[int] = Query(None, description="按仓库 ID 过滤"),
        supplier_id: Optional[int] = Query(None, description="按供应商 ID 过滤"),
        status: Optional[str] = Query(
            None,
            description="按采购单状态过滤，例如 CREATED / PARTIAL / RECEIVED / CLOSED",
        ),
    ) -> List[DailyPurchaseReportItem]:
        """
        按天聚合的采购报表：

        - 聚合维度：采购单创建日期（date）
        - 指标：
            * order_count：当日采购单数
            * total_qty_cases：当日订购件数合计
            * total_units：当日折算最小单位数合计
            * total_amount：当日金额合计
        """
        qty_units_expr = PurchaseOrderLine.qty_ordered * func.coalesce(
            PurchaseOrderLine.units_per_case, 1
        )

        day_expr = func.date(PurchaseOrder.created_at).label("day")

        stmt = (
            select(
                day_expr,
                func.count(distinct(PurchaseOrder.id)).label("order_count"),
                func.coalesce(func.sum(PurchaseOrderLine.qty_ordered), 0).label("total_qty_cases"),
                func.coalesce(func.sum(qty_units_expr), 0).label("total_units"),
                func.coalesce(func.sum(PurchaseOrderLine.line_amount), 0).label(
                    "total_amount",
                ),
            )
            .select_from(PurchaseOrder)
            .join(
                PurchaseOrderLine,
                PurchaseOrderLine.po_id == PurchaseOrder.id,
            )
        )

        stmt = apply_common_filters(
            stmt,
            date_from=date_from,
            date_to=date_to,
            warehouse_id=warehouse_id,
            supplier_id=supplier_id,
            status=status,
        )

        stmt = stmt.group_by(day_expr).order_by(day_expr.asc())

        res = await session.execute(stmt)
        rows = res.all()

        items: List[DailyPurchaseReportItem] = []
        for day_val, order_count, total_qty_cases, total_units, total_amount in rows:
            items.append(
                DailyPurchaseReportItem(
                    day=day_val,
                    order_count=int(order_count or 0),
                    total_qty_cases=int(total_qty_cases or 0),
                    total_units=int(total_units or 0),
                    total_amount=Decimal(str(total_amount or 0)),
                )
            )

        return items
