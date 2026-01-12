# app/api/routers/purchase_reports_routes_items.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.item import Item
from app.models.item_barcode import ItemBarcode
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.schemas.purchase_report import ItemPurchaseReportItem

from app.api.routers.purchase_reports_helpers import apply_common_filters


def register(router: APIRouter) -> None:
    @router.get("/items", response_model=List[ItemPurchaseReportItem])
    async def purchase_report_by_items(
        session: AsyncSession = Depends(get_session),
        date_from: Optional[date] = Query(None, description="起始日期（含），按采购单创建时间过滤"),
        date_to: Optional[date] = Query(None, description="结束日期（含），按采购单创建时间过滤"),
        warehouse_id: Optional[int] = Query(None, description="按仓库 ID 过滤"),
        supplier_id: Optional[int] = Query(None, description="按供应商 ID 过滤"),
        status: Optional[str] = Query(
            None,
            description="按采购单状态过滤，例如 CREATED / PARTIAL / RECEIVED / CLOSED",
        ),
        item_keyword: Optional[str] = Query(
            None,
            description="按商品名称/条码/SKU 模糊匹配（items.name / items.sku / 主条码）",
        ),
    ) -> List[ItemPurchaseReportItem]:
        qty_units_expr = PurchaseOrderLine.qty_ordered * func.coalesce(
            PurchaseOrderLine.units_per_case, 1
        )

        # 主条码子查询：按 item_id 聚合为一行（防御性：max(barcode)）
        primary_bc = (
            select(
                ItemBarcode.item_id.label("item_id"),
                func.max(ItemBarcode.barcode).label("barcode"),
            )
            .where(
                ItemBarcode.active.is_(True),
                ItemBarcode.is_primary.is_(True),
            )
            .group_by(ItemBarcode.item_id)
            .subquery()
        )

        stmt = (
            select(
                PurchaseOrderLine.item_id.label("item_id"),
                Item.sku.label("item_sku"),
                Item.name.label("item_name"),
                func.max(primary_bc.c.barcode).label("barcode"),
                Item.brand.label("brand"),
                Item.category.label("category"),
                PurchaseOrderLine.spec_text.label("spec_text"),
                PurchaseOrder.supplier_id.label("supplier_id"),
                func.coalesce(PurchaseOrder.supplier_name, PurchaseOrder.supplier).label(
                    "supplier_name"
                ),
                func.count(distinct(PurchaseOrder.id)).label("order_count"),
                func.coalesce(func.sum(PurchaseOrderLine.qty_ordered), 0).label(
                    "total_qty_cases"
                ),
                func.coalesce(func.sum(qty_units_expr), 0).label("total_units"),
                func.coalesce(func.sum(PurchaseOrderLine.line_amount), 0).label(
                    "total_amount"
                ),
            )
            .select_from(PurchaseOrder)
            .join(PurchaseOrderLine, PurchaseOrderLine.po_id == PurchaseOrder.id)
            .join(Item, Item.id == PurchaseOrderLine.item_id)
            .outerjoin(primary_bc, primary_bc.c.item_id == Item.id)
        )

        stmt = apply_common_filters(
            stmt,
            date_from=date_from,
            date_to=date_to,
            warehouse_id=warehouse_id,
            supplier_id=supplier_id,
            status=status,
        )

        # ✅ 新增：商品关键词过滤（严格后端执行）
        if item_keyword and str(item_keyword).strip():
            kw = f"%{str(item_keyword).strip()}%"
            stmt = stmt.where(
                or_(
                    Item.name.ilike(kw),
                    Item.sku.ilike(kw),
                    primary_bc.c.barcode.ilike(kw),
                )
            )

        stmt = (
            stmt.group_by(
                PurchaseOrderLine.item_id,
                Item.sku,
                Item.name,
                Item.brand,
                Item.category,
                PurchaseOrderLine.spec_text,
                PurchaseOrder.supplier_id,
                func.coalesce(PurchaseOrder.supplier_name, PurchaseOrder.supplier),
            )
            .order_by(PurchaseOrderLine.item_id.asc())
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
                avg_unit_price = (total_amount_dec / total_units_int).quantize(
                    Decimal("0.0001"),
                )
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
