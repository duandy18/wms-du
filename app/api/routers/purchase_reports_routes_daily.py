# app/api/routers/purchase_reports_routes_daily.py
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
from app.schemas.purchase_report import DailyPurchaseReportItem


def register(router: APIRouter) -> None:
    @router.get("/daily", response_model=List[DailyPurchaseReportItem])
    async def purchase_report_daily(
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
    ) -> List[DailyPurchaseReportItem]:
        """
        按天聚合的采购报表（Receipt 事实口径）：

        - 统计事实来源：inbound_receipts + inbound_receipt_lines
        - 仅统计 source_type=PO 的收货事实
        - 时间口径（time_mode）：
            * occurred（默认）：按收货发生时间（InboundReceipt.occurred_at）
            * po_created：按 PO 创建时间（PurchaseOrder.created_at）作为维度切片
            * po_purchase_time：按 PO 采购时间（PurchaseOrder.purchase_time）作为维度切片
          注意：无论选哪个 time_mode，统计指标都只来自 Receipt（不从 PO/PO line 统计）。
        """
        # 时间维度表达式
        if time_mode == "po_created":
            day_expr = func.date(PurchaseOrder.created_at).label("day")
        elif time_mode == "po_purchase_time":
            day_expr = func.date(PurchaseOrder.purchase_time).label("day")
        else:
            day_expr = func.date(InboundReceipt.occurred_at).label("day")

        stmt = (
            select(
                day_expr,
                # order_count：为了保持历史字段名不破坏前端，含义改为“当日发生收货的 PO 数（distinct po_id）”
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
