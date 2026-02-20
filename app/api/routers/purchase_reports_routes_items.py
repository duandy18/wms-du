# app/api/routers/purchase_reports_routes_items.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, distinct, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.purchase_reports_helpers import apply_common_filters, time_mode_query
from app.db.session import get_session
from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.item import Item
from app.models.item_barcode import ItemBarcode
from app.models.item_test_set import ItemTestSet
from app.models.item_test_set_item import ItemTestSetItem
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.schemas.purchase_report import ItemPurchaseReportItem


def register(router: APIRouter) -> None:
    @router.get("/items", response_model=List[ItemPurchaseReportItem])
    async def purchase_report_by_items(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        supplier_id: Optional[int] = Query(None),
        status: Optional[str] = Query(None),
        item_id: Optional[int] = Query(None),
        item_keyword: Optional[str] = Query(None),
        mode: Literal["fact", "plan"] = Query("fact"),
        time_mode: str = time_mode_query("occurred"),
    ) -> List[ItemPurchaseReportItem]:

        default_set_id_sq = (
            select(ItemTestSet.id).where(ItemTestSet.code == "DEFAULT").limit(1).scalar_subquery()
        )

        main_barcode_expr = (
            select(ItemBarcode.barcode)
            .where(ItemBarcode.item_id == Item.id, ItemBarcode.active.is_(True))
            .order_by(ItemBarcode.is_primary.desc(), ItemBarcode.id.asc())
            .limit(1)
            .scalar_subquery()
        )

        # ================================
        # FACT 口径（基于 inbound_receipts）
        # ================================
        if mode == "fact":
            supplier_name_expr = func.coalesce(InboundReceipt.supplier_name, "").label(
                "supplier_name"
            )

            stmt = (
                select(
                    InboundReceiptLine.item_id.label("item_id"),
                    Item.sku.label("item_sku"),
                    Item.name.label("item_name"),
                    main_barcode_expr.label("barcode"),
                    Item.brand.label("brand"),
                    Item.category.label("category"),
                    func.max(InboundReceiptLine.spec_text).label("spec_text"),
                    InboundReceipt.supplier_id.label("supplier_id"),
                    supplier_name_expr,
                    func.count(distinct(InboundReceipt.source_id)).label("order_count"),
                    func.coalesce(func.sum(InboundReceiptLine.qty_received), 0).label(
                        "total_qty_cases"
                    ),
                    func.coalesce(func.sum(InboundReceiptLine.qty_units), 0).label("total_units"),
                    func.coalesce(func.sum(InboundReceiptLine.line_amount), 0).label(
                        "total_amount"
                    ),
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

            if item_id is not None:
                stmt = stmt.where(InboundReceiptLine.item_id == int(item_id))
            elif item_keyword and str(item_keyword).strip():
                kw = f"%{str(item_keyword).strip()}%"
                stmt = stmt.where(
                    or_(
                        Item.name.ilike(kw),
                        Item.sku.ilike(kw),
                        main_barcode_expr.ilike(kw),
                    )
                )

            stmt = stmt.group_by(
                InboundReceiptLine.item_id,
                Item.sku,
                Item.name,
                Item.brand,
                Item.category,
                InboundReceipt.supplier_id,
                supplier_name_expr,
                main_barcode_expr,
            ).order_by(InboundReceiptLine.item_id.asc())

            rows = (await session.execute(stmt)).all()

            items: List[ItemPurchaseReportItem] = []
            for (
                item_id_val,
                item_sku,
                item_name,
                barcode,
                brand,
                category,
                spec_text,
                supplier_id_val,
                supplier_name,
                order_count,
                total_qty_cases,
                total_units,
                total_amount,
            ) in rows:
                total_units_int = int(total_units or 0)
                total_amount_dec = Decimal(str(total_amount or 0))
                avg_unit_price = (
                    (total_amount_dec / total_units_int).quantize(Decimal("0.0001"))
                    if total_units_int > 0
                    else None
                )

                items.append(
                    ItemPurchaseReportItem(
                        item_id=int(item_id_val),
                        item_sku=item_sku,
                        item_name=item_name,
                        barcode=barcode,
                        brand=brand,
                        category=category,
                        spec_text=spec_text,
                        supplier_id=supplier_id_val,
                        supplier_name=supplier_name,
                        order_count=int(order_count or 0),
                        total_qty_cases=int(total_qty_cases or 0),
                        total_units=total_units_int,
                        total_amount=total_amount_dec,
                        avg_unit_price=avg_unit_price,
                    )
                )
            return items

        # ================================
        # PLAN 口径（supplier 自由文本已废除）
        # ================================
        supplier_name_expr = func.coalesce(
            PurchaseOrder.supplier_name, ""
        ).label("supplier_name")

        line_amount_expr = func.coalesce(PurchaseOrderLine.qty_ordered_base, 0) * func.coalesce(
            PurchaseOrderLine.supply_price, 0
        ) - func.coalesce(PurchaseOrderLine.discount_amount, 0)

        total_units_expr = func.coalesce(
            func.sum(func.coalesce(PurchaseOrderLine.qty_ordered_base, 0)), 0
        )
        total_qty_cases_expr = func.coalesce(func.sum(PurchaseOrderLine.qty_ordered), 0)
        total_amount_expr = func.coalesce(func.sum(line_amount_expr), 0)

        stmt = (
            select(
                PurchaseOrderLine.item_id.label("item_id"),
                Item.sku.label("item_sku"),
                Item.name.label("item_name"),
                main_barcode_expr.label("barcode"),
                Item.brand.label("brand"),
                Item.category.label("category"),
                func.max(PurchaseOrderLine.spec_text).label("spec_text"),
                PurchaseOrder.supplier_id.label("supplier_id"),
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
        if item_id is not None:
            stmt = stmt.where(PurchaseOrderLine.item_id == int(item_id))
        elif item_keyword and str(item_keyword).strip():
            kw = f"%{str(item_keyword).strip()}%"
            stmt = stmt.where(
                or_(
                    Item.name.ilike(kw),
                    Item.sku.ilike(kw),
                    main_barcode_expr.ilike(kw),
                )
            )

        stmt = stmt.group_by(
            PurchaseOrderLine.item_id,
            Item.sku,
            Item.name,
            Item.brand,
            Item.category,
            PurchaseOrder.supplier_id,
            supplier_name_expr,
            main_barcode_expr,
        ).order_by(PurchaseOrderLine.item_id.asc())

        rows = (await session.execute(stmt)).all()

        items: List[ItemPurchaseReportItem] = []
        for (
            item_id_val,
            item_sku,
            item_name,
            barcode,
            brand,
            category,
            spec_text,
            supplier_id_val,
            supplier_name,
            order_count,
            total_qty_cases,
            total_units,
            total_amount,
        ) in rows:
            total_units_int = int(total_units or 0)
            total_amount_dec = Decimal(str(total_amount or 0))
            avg_unit_price = (
                (total_amount_dec / total_units_int).quantize(Decimal("0.0001"))
                if total_units_int > 0
                else None
            )

            items.append(
                ItemPurchaseReportItem(
                    item_id=int(item_id_val),
                    item_sku=item_sku,
                    item_name=item_name,
                    barcode=barcode,
                    brand=brand,
                    category=category,
                    spec_text=spec_text,
                    supplier_id=supplier_id_val,
                    supplier_name=supplier_name,
                    order_count=int(order_count or 0),
                    total_qty_cases=int(total_qty_cases or 0),
                    total_units=total_units_int,
                    total_amount=total_amount_dec,
                    avg_unit_price=avg_unit_price,
                )
            )

        return items
