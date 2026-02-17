# app/api/routers/purchase_reports_routes_daily.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.purchase_reports_helpers import apply_common_filters, time_mode_query
from app.db.session import get_session
from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.item import Item
from app.models.item_test_set import ItemTestSet
from app.models.item_test_set_item import ItemTestSetItem
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.schemas.purchase_report import DailyPurchaseReportItem


def register(router: APIRouter) -> None:
    @router.get("/daily", response_model=List[DailyPurchaseReportItem])
    async def purchase_report_daily(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        supplier_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        mode: Literal["fact", "plan"] = Query("fact"),
        time_mode: str = time_mode_query("occurred"),
    ) -> List[DailyPurchaseReportItem]:

        default_set_id_sq = (
            select(ItemTestSet.id)
            .where(ItemTestSet.code == "DEFAULT")
            .limit(1)
            .scalar_subquery()
        )

        # ================================
        # FACT 口径（基于 inbound_receipts）
        # ================================
        if mode == "fact":
            if time_mode == "po_created":
                day_expr = func.date(PurchaseOrder.created_at).label("day")
            elif time_mode == "po_purchase_time":
                day_expr = func.date(PurchaseOrder.purchase_time).label("day")
            else:
                day_expr = func.date(InboundReceipt.occurred_at).label("day")

            stmt = (
                select(
                    day_expr,
                    func.count(distinct(InboundReceipt.source_id)).label("order_count"),
                    func.coalesce(func.sum(InboundReceiptLine.qty_received), 0).label("total_qty_cases"),
                    func.coalesce(func.sum(InboundReceiptLine.qty_units), 0).label("total_units"),
                    func.coalesce(func.sum(InboundReceiptLine.line_amount), 0).label("total_amount"),
                )
                .select_from(InboundReceipt)
                .join(InboundReceiptLine, InboundReceiptLine.receipt_id == InboundReceipt.id)
                .join(PurchaseOrder, PurchaseOrder.id == InboundReceipt.source_id)
                .join(Item, Item.id == InboundReceiptLine.item_id)
                .outerjoin(
                    ItemTestSetItem,
                    and_(
                        ItemTestSetItem.item_id == Item.id,
                        ItemTestSetItem.set_id == default_set_id_sq,
                    ),
                )
                .where(InboundReceipt.source_type == "PO")
                .where(InboundReceipt.status == "CONFIRMED")
                .where(ItemTestSetItem.id.is_(None))
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

            rows = (await session.execute(stmt)).all()

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

        # ================================
        # PLAN 口径（不变）
        # ================================
        if time_mode == "po_created":
            day_expr = func.date(PurchaseOrder.created_at).label("day")
            time_col = PurchaseOrder.created_at
        else:
            day_expr = func.date(PurchaseOrder.purchase_time).label("day")
            time_col = PurchaseOrder.purchase_time

        line_amount_expr = func.coalesce(
            PurchaseOrderLine.line_amount,
            (
                PurchaseOrderLine.qty_ordered
                * func.coalesce(PurchaseOrderLine.units_per_case, 1)
                * func.coalesce(PurchaseOrderLine.supply_price, 0)
            ),
        )

        stmt = (
            select(
                day_expr,
                func.count(distinct(PurchaseOrder.id)).label("order_count"),
                func.coalesce(func.sum(PurchaseOrderLine.qty_ordered), 0).label("total_qty_cases"),
                func.coalesce(
                    func.sum(
                        PurchaseOrderLine.qty_ordered
                        * func.coalesce(PurchaseOrderLine.units_per_case, 1)
                    ),
                    0,
                ).label("total_units"),
                func.coalesce(func.sum(line_amount_expr), 0).label("total_amount"),
            )
            .select_from(PurchaseOrder)
            .join(PurchaseOrderLine, PurchaseOrderLine.po_id == PurchaseOrder.id)
            .join(Item, Item.id == PurchaseOrderLine.item_id)
            .outerjoin(
                ItemTestSetItem,
                and_(
                    ItemTestSetItem.item_id == Item.id,
                    ItemTestSetItem.set_id == default_set_id_sq,
                ),
            )
            .where(ItemTestSetItem.id.is_(None))
        )

        if date_from is not None:
            stmt = stmt.where(func.date(time_col) >= date_from)
        if date_to is not None:
            stmt = stmt.where(func.date(time_col) <= date_to)
        if warehouse_id is not None:
            stmt = stmt.where(PurchaseOrder.warehouse_id == int(warehouse_id))
        if supplier_id is not None:
            stmt = stmt.where(PurchaseOrder.supplier_id == int(supplier_id))
        if status:
            stmt = stmt.where(PurchaseOrder.status == status.strip().upper())

        stmt = stmt.group_by(day_expr).order_by(day_expr.asc())

        rows = (await session.execute(stmt)).all()

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
