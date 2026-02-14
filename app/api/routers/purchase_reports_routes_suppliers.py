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
from app.models.receive_task import ReceiveTask
from app.schemas.purchase_report import SupplierPurchaseReportItem


def register(router: APIRouter) -> None:
    @router.get("/suppliers", response_model=List[SupplierPurchaseReportItem])
    async def purchase_report_by_suppliers(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None, description="起始日期（含）"),
        date_to: Optional[date] = Query(None, description="结束日期（含）"),
        warehouse_id: Optional[int] = Query(None, description="按仓库 ID 过滤"),
        supplier_id: Optional[int] = Query(None, description="按供应商 ID 过滤"),
        status: Optional[str] = Query(
            None,
            description="按采购单状态过滤，例如 CREATED / PARTIAL / RECEIVED / CLOSED",
        ),
        mode: Literal["fact", "plan"] = Query(
            "fact",
            description="口径：fact=收货事实（Receipt）；plan=下单计划（PO）",
        ),
        time_mode: str = time_mode_query("occurred"),
    ) -> List[SupplierPurchaseReportItem]:
        """
        供应商维度采购报表——统计口径 PROD-only（排除 DEFAULT Test Set 商品）
        """

        default_set_id_sq = (
            select(ItemTestSet.id)
            .where(ItemTestSet.code == "DEFAULT")
            .limit(1)
            .scalar_subquery()
        )

        # -----------------------------
        # fact：Receipt 事实口径（原逻辑 + PROD-only 过滤）
        # -----------------------------
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
                .join(Item, Item.id == InboundReceiptLine.item_id)
                .outerjoin(
                    ItemTestSetItem,
                    and_(
                        ItemTestSetItem.item_id == Item.id,
                        ItemTestSetItem.set_id == default_set_id_sq,
                    ),
                )
                .outerjoin(ReceiveTask, ReceiveTask.id == InboundReceipt.receive_task_id)
                .outerjoin(PurchaseOrder, PurchaseOrder.id == ReceiveTask.po_id)
                .where(InboundReceipt.source_type == "PO")
                .where(ItemTestSetItem.id.is_(None))  # ✅ PROD-only
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

        # -----------------------------
        # plan：PO 下单计划口径（原逻辑 + PROD-only 过滤）
        # -----------------------------
        supplier_name_expr = func.coalesce(PurchaseOrder.supplier_name, PurchaseOrder.supplier, "").label("supplier_name")

        line_amount_expr = func.coalesce(
            PurchaseOrderLine.line_amount,
            (PurchaseOrderLine.qty_ordered * func.coalesce(PurchaseOrderLine.units_per_case, 1) * func.coalesce(PurchaseOrderLine.supply_price, 0)),
        )

        total_units_expr = func.coalesce(
            func.sum(PurchaseOrderLine.qty_ordered * func.coalesce(PurchaseOrderLine.units_per_case, 1)), 0
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
            .where(ItemTestSetItem.id.is_(None))  # ✅ PROD-only
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
