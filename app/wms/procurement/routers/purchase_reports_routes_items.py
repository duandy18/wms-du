# app/wms/procurement/routers/purchase_reports_routes_items.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, distinct, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.procurement.helpers.purchase_reports import apply_common_filters, time_mode_query
from app.db.session import get_session
from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.item import Item
from app.models.item_barcode import ItemBarcode
from app.models.item_test_set import ItemTestSet
from app.models.item_test_set_item import ItemTestSetItem
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.wms.procurement.contracts.purchase_report import ItemPurchaseReportItem


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
                    supplier_name_expr,
                    func.count(distinct(InboundReceipt.source_id)).label("order_count"),
                    func.coalesce(func.sum(InboundReceiptLine.qty_base), 0).label(
                        "total_units"
                    ),
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
                supplier_name,
                order_count,
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
                        supplier_name=supplier_name,
                        order_count=int(order_count or 0),
                        total_units=total_units_int,
                        total_amount=total_amount_dec,
                        avg_unit_price=avg_unit_price,
                    )
                )
            return items

        # PLAN 模式（全部基于 base）
        supplier_name_expr = func.coalesce(
            PurchaseOrder.supplier_name, ""
        ).label("supplier_name")

        stmt = (
            select(
                PurchaseOrderLine.item_id.label("item_id"),
                Item.sku.label("item_sku"),
                Item.name.label("item_name"),
                supplier_name_expr,
                func.count(distinct(PurchaseOrder.id)).label("order_count"),
                func.coalesce(func.sum(PurchaseOrderLine.qty_ordered_base), 0).label(
                    "total_units"
                ),
            )
            .select_from(PurchaseOrder)
            .join(PurchaseOrderLine, PurchaseOrderLine.po_id == PurchaseOrder.id)
            .join(Item, Item.id == PurchaseOrderLine.item_id)
        )

        stmt = stmt.group_by(
            PurchaseOrderLine.item_id,
            Item.sku,
            Item.name,
            supplier_name_expr,
        )

        rows = (await session.execute(stmt)).all()

        return [
            ItemPurchaseReportItem(
                item_id=int(r[0]),
                item_sku=r[1],
                item_name=r[2],
                supplier_name=r[3],
                order_count=int(r[4] or 0),
                total_units=int(r[5] or 0),
                total_amount=None,
                avg_unit_price=None,
            )
            for r in rows
        ]
