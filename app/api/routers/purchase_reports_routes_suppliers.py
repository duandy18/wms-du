# app/api/routers/purchase_reports_routes_suppliers.py
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
from app.schemas.purchase_report import SupplierPurchaseReportItem


def register(router: APIRouter) -> None:
    @router.get("/suppliers", response_model=List[SupplierPurchaseReportItem])
    async def purchase_report_by_suppliers(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        supplier_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        mode: Literal["fact", "plan"] = Query("fact"),
        time_mode: str = time_mode_query("occurred"),
    ) -> List[SupplierPurchaseReportItem]:

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
            supplier_name_expr = func.coalesce(InboundReceipt.supplier_name, "").label("supplier_name")

            stmt = (
                select(
                    InboundReceipt.supplier_id,
                    supplier_name_expr,
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

            stmt = stmt.group_by(
                InboundReceipt.supplier_id,
                supplier_name_expr,
            ).order_by("supplier_name")

            rows = (await session.execute(stmt)).all()

            items: List[SupplierPurchaseReportItem] = []
            for supplier_id_val, supplier_name, order_count, total_qty_cases, total_units, total_amount in rows:
                total_units_int = int(total_units or 0)
                total_amount_dec = Decimal(str(total_amount or 0))
                avg_unit_price = (
                    (total_amount_dec / total_units_int).quantize(Decimal("0.0001"))
                    if total_units_int > 0
                    else None
                )

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

        # ================================
        # PLAN 口径（保持原逻辑）
        # ================================
        supplier_name_expr = func.coalesce(
            PurchaseOrder.supplier_name,
            PurchaseOrder.supplier,
            "",
        ).label("supplier_name")

        line_amount_expr = func.coalesce(
            PurchaseOrderLine.line_amount,
            (
                PurchaseOrderLine.qty_ordered
                * func.coalesce(PurchaseOrderLine.units_per_case, 1)
                * func.coalesce(PurchaseOrderLine.supply_price, 0)
            ),
        )

        total_units_expr = func.coalesce(
            func.sum(
                PurchaseOrderLine.qty_ordered
                * func.coalesce(PurchaseOrderLine.units_per_case, 1)
            ),
            0,
        )
        total_qty_cases_expr = func.coalesce(func.sum(PurchaseOrderLine.qty_ordered), 0)
        total_amount_expr = func.coalesce(func.sum(line_amount_expr), 0)

        stmt = (
            select(
                PurchaseOrder.supplier_id,
                supplier_name_expr,
                func.count(distinct(PurchaseOrder.id)).label("order_count"),
                total_qty_cases_expr.label("total_qty_cases"),
                total_units_expr.label("total_units"),
                total_amount_expr.label("total_amount"),
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

        if time_mode == "po_created":
            time_col = PurchaseOrder.created_at
        else:
            time_col = PurchaseOrder.purchase_time

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

        stmt = stmt.group_by(PurchaseOrder.supplier_id, supplier_name_expr).order_by("supplier_name")

        rows = (await session.execute(stmt)).all()

        items: List[SupplierPurchaseReportItem] = []
        for supplier_id_val, supplier_name, order_count, total_qty_cases, total_units, total_amount in rows:
            total_units_int = int(total_units or 0)
            total_amount_dec = Decimal(str(total_amount or 0))
            avg_unit_price = (
                (total_amount_dec / total_units_int).quantize(Decimal("0.0001"))
                if total_units_int > 0
                else None
            )

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
