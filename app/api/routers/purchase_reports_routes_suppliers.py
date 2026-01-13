# app/api/routers/purchase_reports_routes_suppliers.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.purchase_reports_helpers import apply_common_filters, time_mode_query
from app.db.session import get_session
from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.purchase_order import PurchaseOrder
from app.models.receive_task import ReceiveTask
from app.schemas.purchase_report import SupplierPurchaseReportItem


def register(router: APIRouter) -> None:
    @router.get("/suppliers", response_model=List[SupplierPurchaseReportItem])
    async def purchase_report_by_suppliers(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None, description="起始日期（含）"),
        date_to: Optional[date] = Query(None, description="结束日期（含）"),
        warehouse_id: Optional[int] = Query(None, description="按仓库 ID 过滤（事实维度）"),
        supplier_id: Optional[int] = Query(None, description="按供应商 ID 过滤（事实维度）"),
        status: Optional[str] = Query(
            None,
            description="按采购单状态过滤（维度），例如 CREATED / PARTIAL / RECEIVED / CLOSED",
        ),
        time_mode: str = time_mode_query("occurred"),
    ) -> List[SupplierPurchaseReportItem]:
        """
        按供应商聚合的采购报表（Receipt 事实口径）：

        - 统计事实来源：inbound_receipts + inbound_receipt_lines
        - 仅统计 source_type=PO 的收货事实
        - supplier 维度优先使用 InboundReceipt.supplier_id/supplier_name（事实快照）
        """
        # ⚠️ 关键：必须复用同一个表达式对象（否则会变成不同 bindparam，PG 会报 grouping error）
        supplier_name_expr = func.coalesce(InboundReceipt.supplier_name, "").label("supplier_name")

        stmt = (
            select(
                InboundReceipt.supplier_id,
                supplier_name_expr,
                # order_count：发生收货事实的 PO 数（distinct po_id）
                func.count(distinct(InboundReceipt.source_id)).label("order_count"),
                func.coalesce(func.sum(InboundReceiptLine.qty_received), 0).label("total_qty_cases"),
                func.coalesce(func.sum(InboundReceiptLine.qty_units), 0).label("total_units"),
                func.coalesce(func.sum(InboundReceiptLine.line_amount), 0).label("total_amount"),
            )
            .select_from(InboundReceipt)
            .join(InboundReceiptLine, InboundReceiptLine.receipt_id == InboundReceipt.id)
            # 维度 join（只用于 status / po_* 时间维度；不作为统计来源）
            .outerjoin(ReceiveTask, ReceiveTask.id == InboundReceipt.receive_task_id)
            .outerjoin(PurchaseOrder, PurchaseOrder.id == ReceiveTask.po_id)
            .where(InboundReceipt.source_type == "PO")
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

        stmt = stmt.group_by(
            InboundReceipt.supplier_id,
            supplier_name_expr,
        ).order_by("supplier_name")

        res = await session.execute(stmt)
        rows = res.all()

        items: List[SupplierPurchaseReportItem] = []
        for supplier_id_val, supplier_name, order_count, total_qty_cases, total_units, total_amount in rows:
            total_units_int = int(total_units or 0)
            total_amount_dec = Decimal(str(total_amount or 0))

            avg_unit_price: Optional[Decimal]
            if total_units_int > 0:
                avg_unit_price = (total_amount_dec / total_units_int).quantize(Decimal("0.0001"))
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
