# app/api/routers/purchase_reports_routes_suppliers.py
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
from app.schemas.purchase_report import SupplierPurchaseReportItem

from app.api.routers.purchase_reports_helpers import apply_common_filters


def register(router: APIRouter) -> None:
    @router.get("/suppliers", response_model=List[SupplierPurchaseReportItem])
    async def purchase_report_by_suppliers(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None, description="起始日期（含），按采购单创建时间过滤"),
        date_to: Optional[date] = Query(None, description="结束日期（含），按采购单创建时间过滤"),
        warehouse_id: Optional[int] = Query(None, description="按仓库 ID 过滤"),
        supplier_id: Optional[int] = Query(None, description="按供应商 ID 过滤"),
        status: Optional[str] = Query(
            None,
            description="按采购单状态过滤，例如 CREATED / PARTIAL / RECEIVED / CLOSED",
        ),
    ) -> List[SupplierPurchaseReportItem]:
        """
        按供应商聚合的采购报表：

        - 聚合维度：supplier_id + supplier_name（supplier_name 为空时回退 supplier）
        - 指标：
            * order_count：采购单数量
            * total_qty_cases：订购件数合计（qty_ordered 之和）
            * total_units：折算最小单位数量合计（qty_ordered × units_per_case，缺省 units_per_case=1）
            * total_amount：行金额合计（优先使用 line_amount，否则 qty_ordered × units_per_case × supply_price）
            * avg_unit_price：金额 / 最小单位数
        """
        # qty_units = qty_ordered * COALESCE(units_per_case, 1)
        qty_units_expr = PurchaseOrderLine.qty_ordered * func.coalesce(
            PurchaseOrderLine.units_per_case, 1
        )

        stmt = (
            select(
                PurchaseOrder.supplier_id,
                func.coalesce(PurchaseOrder.supplier_name, PurchaseOrder.supplier).label(
                    "supplier_name"
                ),
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

        stmt = stmt.group_by(
            PurchaseOrder.supplier_id,
            func.coalesce(PurchaseOrder.supplier_name, PurchaseOrder.supplier),
        ).order_by("supplier_name")

        res = await session.execute(stmt)
        rows = res.all()

        items: List[SupplierPurchaseReportItem] = []
        for (
            supplier_id_val,
            supplier_name,
            order_count,
            total_qty_cases,
            total_units,
            total_amount,
        ) in rows:
            total_units_int = int(total_units or 0)
            total_amount_dec = Decimal(str(total_amount or 0))
            avg_unit_price: Optional[Decimal]
            if total_units_int > 0 and total_amount_dec is not None:
                avg_unit_price = (total_amount_dec / total_units_int).quantize(
                    Decimal("0.0001"),
                )
            else:
                avg_unit_price = None

            items.append(
                SupplierPurchaseReportItem(
                    supplier_id=supplier_id_val,
                    supplier_name=supplier_name or "",
                    order_count=int(order_count or 0),
                    total_qty_cases=int(total_qty_cases or 0),
                    total_units=total_units_int,
                    total_amount=total_amount_dec,
                    avg_unit_price=avg_unit_price,
                )
            )

        return items
