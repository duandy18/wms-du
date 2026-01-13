# app/api/routers/purchase_reports_routes_items.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.purchase_reports_helpers import apply_common_filters, time_mode_query
from app.db.session import get_session
from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.item import Item
from app.models.item_barcode import ItemBarcode
from app.models.purchase_order import PurchaseOrder
from app.models.receive_task import ReceiveTask
from app.schemas.purchase_report import ItemPurchaseReportItem


def register(router: APIRouter) -> None:
    @router.get("/items", response_model=List[ItemPurchaseReportItem])
    async def purchase_report_by_items(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None, description="起始日期（含）"),
        date_to: Optional[date] = Query(None, description="结束日期（含）"),
        warehouse_id: Optional[int] = Query(None, description="按仓库 ID 过滤（事实维度）"),
        supplier_id: Optional[int] = Query(None, description="按供应商 ID 过滤（事实维度）"),
        status: Optional[str] = Query(
            None,
            description="按采购单状态过滤（维度），例如 CREATED / PARTIAL / RECEIVED / CLOSED",
        ),
        item_keyword: Optional[str] = Query(
            None,
            description="按商品名称/条码/SKU 模糊匹配（items.name / items.sku / 主条码）",
        ),
        time_mode: str = time_mode_query("occurred"),
    ) -> List[ItemPurchaseReportItem]:
        # 主条码表达式（与 snapshot_inventory.py 同口径）
        main_barcode_expr = (
            select(ItemBarcode.barcode)
            .where(ItemBarcode.item_id == Item.id, ItemBarcode.active.is_(True))
            .order_by(ItemBarcode.is_primary.desc(), ItemBarcode.id.asc())
            .limit(1)
            .scalar_subquery()
        )

        supplier_name_expr = func.coalesce(InboundReceipt.supplier_name, "").label("supplier_name")

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
                func.coalesce(func.sum(InboundReceiptLine.qty_received), 0).label("total_qty_cases"),
                func.coalesce(func.sum(InboundReceiptLine.qty_units), 0).label("total_units"),
                func.coalesce(func.sum(InboundReceiptLine.line_amount), 0).label("total_amount"),
            )
            .select_from(InboundReceipt)
            .join(InboundReceiptLine, InboundReceiptLine.receipt_id == InboundReceipt.id)
            .join(Item, Item.id == InboundReceiptLine.item_id)
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

        if item_keyword and str(item_keyword).strip():
            kw = f"%{str(item_keyword).strip()}%"
            stmt = stmt.where(
                or_(
                    Item.name.ilike(kw),
                    Item.sku.ilike(kw),
                    main_barcode_expr.ilike(kw),
                )
            )

        stmt = (
            stmt.group_by(
                InboundReceiptLine.item_id,
                Item.sku,
                Item.name,
                Item.brand,
                Item.category,
                InboundReceipt.supplier_id,
                supplier_name_expr,
                main_barcode_expr,
            )
            .order_by(InboundReceiptLine.item_id.asc())
        )

        res = await session.execute(stmt)
        rows = res.all()

        items: List[ItemPurchaseReportItem] = []
        for (
            item_id,
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

            avg_unit_price: Optional[Decimal]
            if total_units_int > 0:
                avg_unit_price = (total_amount_dec / total_units_int).quantize(Decimal("0.0001"))
            else:
                avg_unit_price = None

            items.append(
                ItemPurchaseReportItem(
                    item_id=int(item_id),
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
