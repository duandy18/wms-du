# app/procurement/routers/purchase_reports_routes_items.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.pms.public.items.services.item_read_service import ItemReadService
from app.procurement.contracts.purchase_report import ItemPurchaseReportItem
from app.procurement.helpers.purchase_reports import (
    apply_common_filters,
    resolve_report_item_ids,
    time_mode_query,
)
from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.models.purchase_order_line_completion import PurchaseOrderLineCompletion


def _build_report_item(
    *,
    item_id_val: int,
    item_sku: str | None,
    item_name: str | None,
    barcode: str | None,
    brand: str | None,
    category: str | None,
    spec_text: str | None,
    supplier_id: int | None,
    supplier_name: str | None,
    order_count: int,
    total_qty_cases: int,
    total_units: int,
    total_amount: Decimal | None,
    avg_unit_price: Decimal | None,
) -> ItemPurchaseReportItem:
    return ItemPurchaseReportItem(
        item_id=int(item_id_val),
        item_sku=item_sku,
        item_name=item_name,
        barcode=barcode,
        brand=brand,
        category=category,
        spec_text=spec_text,
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        order_count=int(order_count or 0),
        total_qty_cases=int(total_qty_cases or 0),
        total_units=int(total_units or 0),
        total_amount=total_amount,
        avg_unit_price=avg_unit_price,
    )


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
        time_mode: str = time_mode_query("purchase_time"),
    ) -> List[ItemPurchaseReportItem]:
        report_item_ids = await resolve_report_item_ids(
            session,
            item_id=item_id,
            item_keyword=item_keyword,
        )
        if report_item_ids is not None and not report_item_ids:
            return []

        item_read_svc = ItemReadService(session)

        stmt = (
            select(
                PurchaseOrderLineCompletion.item_id.label("item_id"),
                func.count(distinct(PurchaseOrderLineCompletion.po_id)).label("order_count"),
                func.coalesce(
                    func.sum(PurchaseOrderLineCompletion.qty_ordered_input),
                    0,
                ).label("total_qty_cases"),
                func.coalesce(
                    func.sum(PurchaseOrderLineCompletion.qty_ordered_base),
                    0,
                ).label("total_units"),
                func.coalesce(
                    func.sum(PurchaseOrderLineCompletion.planned_line_amount),
                    0,
                ).label("total_amount"),
                func.min(PurchaseOrderLineCompletion.supplier_id).label("supplier_id_for_filtered"),
                func.min(
                    func.coalesce(PurchaseOrderLineCompletion.supplier_name, "")
                ).label("supplier_name_for_filtered"),
            )
            .select_from(PurchaseOrderLineCompletion)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLineCompletion.po_id)
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

        if report_item_ids is not None:
            stmt = stmt.where(PurchaseOrderLineCompletion.item_id.in_(report_item_ids))

        stmt = stmt.group_by(
            PurchaseOrderLineCompletion.item_id,
        ).order_by(PurchaseOrderLineCompletion.item_id.asc())

        rows = (await session.execute(stmt)).mappings().all()
        if not rows:
            return []

        meta_map = await item_read_svc.aget_report_meta_by_item_ids(
            item_ids=[int(r["item_id"]) for r in rows]
        )

        items: List[ItemPurchaseReportItem] = []
        for row in rows:
            item_id_val = int(row["item_id"])
            total_qty_cases = int(row["total_qty_cases"] or 0)
            total_units = int(row["total_units"] or 0)
            total_amount = Decimal(str(row["total_amount"] or 0))
            avg_unit_price = (
                (total_amount / total_units).quantize(Decimal("0.0001"))
                if total_units > 0
                else None
            )
            meta = meta_map.get(item_id_val)

            supplier_id_val: int | None = None
            supplier_name_val: str | None = None
            if supplier_id is not None:
                supplier_id_val = int(row["supplier_id_for_filtered"])
                supplier_name_val = str(row["supplier_name_for_filtered"] or "") or None

            items.append(
                _build_report_item(
                    item_id_val=item_id_val,
                    item_sku=getattr(meta, "sku", None),
                    item_name=getattr(meta, "name", None) or f"ITEM-{item_id_val}",
                    barcode=getattr(meta, "barcode", None),
                    brand=getattr(meta, "brand", None),
                    category=getattr(meta, "category", None),
                    spec_text=getattr(meta, "spec", None) or getattr(meta, "spec_text", None),
                    supplier_id=supplier_id_val,
                    supplier_name=supplier_name_val,
                    order_count=int(row["order_count"] or 0),
                    total_qty_cases=total_qty_cases,
                    total_units=total_units,
                    total_amount=total_amount,
                    avg_unit_price=avg_unit_price,
                )
            )

        return items
