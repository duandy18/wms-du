# app/wms/procurement/routers/purchase_reports_routes_items.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.procurement.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.item_test_set import ItemTestSet
from app.models.item_test_set_item import ItemTestSetItem
from app.procurement.models.purchase_order import PurchaseOrder
from app.procurement.models.purchase_order_line import PurchaseOrderLine
from app.pms.public.items.services.item_read_service import ItemReadService
from app.procurement.contracts.purchase_report import ItemPurchaseReportItem
from app.procurement.helpers.purchase_reports import apply_common_filters, time_mode_query


async def _resolve_report_item_ids(
    session: AsyncSession,
    *,
    item_id: Optional[int],
    item_keyword: Optional[str],
) -> Optional[list[int]]:
    """
    返回：
    - [item_id]：显式 item_id 过滤
    - [ids...]：按 PMS public item 搜索出的 item_id 集合
    - None：不加 item 过滤
    """
    if item_id is not None:
        return [int(item_id)]

    kw = str(item_keyword or "").strip()
    if not kw:
        return None

    svc = ItemReadService(session)
    return await svc.asearch_report_item_ids_by_keyword(keyword=kw)


def _build_report_item(
    *,
    item_id_val: int,
    supplier_name: str | None,
    order_count: int,
    total_units: int,
    total_amount: Decimal | None,
    avg_unit_price: Decimal | None,
    meta,
) -> ItemPurchaseReportItem:
    item_sku = meta.sku if meta is not None else ""
    item_name = meta.name if meta is not None else f"ITEM-{int(item_id_val)}"
    barcode = meta.barcode if meta is not None else None
    brand = meta.brand if meta is not None else None
    category = meta.category if meta is not None else None

    return ItemPurchaseReportItem(
        item_id=int(item_id_val),
        item_sku=item_sku,
        item_name=item_name,
        barcode=barcode,
        brand=brand,
        category=category,
        supplier_name=supplier_name,
        order_count=int(order_count or 0),
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
        mode: Literal["fact", "plan"] = Query("fact"),
        time_mode: str = time_mode_query("occurred"),
    ) -> List[ItemPurchaseReportItem]:

        default_set_id_sq = (
            select(ItemTestSet.id).where(ItemTestSet.code == "DEFAULT").limit(1).scalar_subquery()
        )

        report_item_ids = await _resolve_report_item_ids(
            session,
            item_id=item_id,
            item_keyword=item_keyword,
        )
        if report_item_ids is not None and not report_item_ids:
            return []

        item_read_svc = ItemReadService(session)

        if mode == "fact":
            supplier_name_expr = func.coalesce(InboundReceipt.supplier_name, "").label("supplier_name")

            stmt = (
                select(
                    InboundReceiptLine.item_id.label("item_id"),
                    supplier_name_expr,
                    func.count(distinct(InboundReceipt.source_id)).label("order_count"),
                    func.coalesce(func.sum(InboundReceiptLine.qty_base), 0).label("total_units"),
                    func.coalesce(func.sum(InboundReceiptLine.line_amount), 0).label("total_amount"),
                )
                .select_from(InboundReceipt)
                .join(InboundReceiptLine, InboundReceiptLine.receipt_id == InboundReceipt.id)
                .join(PurchaseOrder, PurchaseOrder.id == InboundReceipt.source_id)
                .outerjoin(
                    ItemTestSetItem,
                    and_(
                        ItemTestSetItem.item_id == InboundReceiptLine.item_id,
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

            if report_item_ids is not None:
                stmt = stmt.where(InboundReceiptLine.item_id.in_(report_item_ids))

            stmt = stmt.group_by(
                InboundReceiptLine.item_id,
                supplier_name_expr,
            ).order_by(InboundReceiptLine.item_id.asc())

            rows = (await session.execute(stmt)).mappings().all()
            if not rows:
                return []

            meta_map = await item_read_svc.aget_report_meta_by_item_ids(
                item_ids=[int(r["item_id"]) for r in rows]
            )

            items: List[ItemPurchaseReportItem] = []
            for row in rows:
                item_id_val = int(row["item_id"])
                total_units_int = int(row["total_units"] or 0)
                total_amount_dec = Decimal(str(row["total_amount"] or 0))
                avg_unit_price = (
                    (total_amount_dec / total_units_int).quantize(Decimal("0.0001"))
                    if total_units_int > 0
                    else None
                )

                items.append(
                    _build_report_item(
                        item_id_val=item_id_val,
                        supplier_name=row["supplier_name"],
                        order_count=int(row["order_count"] or 0),
                        total_units=total_units_int,
                        total_amount=total_amount_dec,
                        avg_unit_price=avg_unit_price,
                        meta=meta_map.get(item_id_val),
                    )
                )
            return items

        # PLAN 模式：本次仅收跨域 item/barcode ORM 直连；
        # 不顺手改既有 plan 过滤语义。
        supplier_name_expr = func.coalesce(PurchaseOrder.supplier_name, "").label("supplier_name")

        stmt = (
            select(
                PurchaseOrderLine.item_id.label("item_id"),
                supplier_name_expr,
                func.count(distinct(PurchaseOrder.id)).label("order_count"),
                func.coalesce(func.sum(PurchaseOrderLine.qty_ordered_base), 0).label("total_units"),
            )
            .select_from(PurchaseOrder)
            .join(PurchaseOrderLine, PurchaseOrderLine.po_id == PurchaseOrder.id)
        )

        stmt = stmt.group_by(
            PurchaseOrderLine.item_id,
            supplier_name_expr,
        )

        rows = (await session.execute(stmt)).mappings().all()
        if not rows:
            return []

        meta_map = await item_read_svc.aget_report_meta_by_item_ids(
            item_ids=[int(r["item_id"]) for r in rows]
        )

        return [
            _build_report_item(
                item_id_val=int(r["item_id"]),
                supplier_name=r["supplier_name"],
                order_count=int(r["order_count"] or 0),
                total_units=int(r["total_units"] or 0),
                total_amount=None,
                avg_unit_price=None,
                meta=meta_map.get(int(r["item_id"])),
            )
            for r in rows
        ]
