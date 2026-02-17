# app/services/purchase_order_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.item_barcode import ItemBarcode
from app.schemas.purchase_order import PurchaseOrderLineOut, PurchaseOrderWithLinesOut
from app.services.inbound_service import InboundService
from app.services.purchase_order_create import create_po_v2 as _create_po_v2
from app.services.purchase_order_queries import get_po_with_lines as _get_po_with_lines
from app.services.purchase_order_receive import receive_po_line as _receive_po_line
from app.services.qty_base import ordered_base as _ordered_base_impl
from app.services.qty_base import received_base as _received_base_impl

UTC = timezone.utc


def _get_qty_ordered_base(ln: Any) -> int:
    """
    ✅ Phase 2：最小单位订购事实（base）
    统一委托 app/services/qty_base.py
    """
    return int(_ordered_base_impl(ln) or 0)


def _get_qty_received_base(ln: Any) -> int:
    """
    ✅ Phase 2：最小单位已收事实（base）
    统一委托 app/services/qty_base.py
    """
    return int(_received_base_impl(ln) or 0)


def _safe_upc(v: Any) -> int:
    try:
        n = int(v or 1)
    except Exception:
        n = 1
    return n if n > 0 else 1


def _base_to_purchase(base_qty: int, upc: int) -> int:
    """
    展示用：把 base 换算为采购单位（向下取整）。
    """
    if upc <= 0:
        return int(base_qty)
    return int(base_qty) // int(upc)


async def _load_items_map(session: AsyncSession, item_ids: List[int]) -> Dict[int, Item]:
    if not item_ids:
        return {}
    rows = (await session.execute(select(Item).where(Item.id.in_(item_ids)))).scalars().all()
    return {int(it.id): it for it in rows}


async def _load_primary_barcodes(session: AsyncSession, item_ids: List[int]) -> Dict[int, str]:
    """
    主条码规则（与 snapshot_inventory.py 保持一致）：
    - 仅 active=true
    - is_primary 优先，否则最小 id（稳定且可解释）
    """
    if not item_ids:
        return {}

    rows = (
        (
            await session.execute(
                select(ItemBarcode)
                .where(ItemBarcode.item_id.in_(item_ids), ItemBarcode.active.is_(True))
                .order_by(
                    ItemBarcode.item_id.asc(),
                    ItemBarcode.is_primary.desc(),
                    ItemBarcode.id.asc(),
                )
            )
        )
        .scalars()
        .all()
    )

    m: Dict[int, str] = {}
    for bc in rows:
        iid = int(bc.item_id)
        if iid in m:
            continue
        m[iid] = bc.barcode
    return m


class PurchaseOrderService:
    """
    采购单服务（Phase 2：唯一形态）

    ✅ 合同加严（关键）：
    - base（最小单位）为唯一事实口径：qty_ordered_base / qty_received_base / qty_remaining_base
    - qty_ordered / qty_received / qty_remaining 为采购单位展示口径（由 base + units_per_case 换算）
    """

    def __init__(self, inbound_svc: Optional[InboundService] = None) -> None:
        self.inbound_svc = inbound_svc or InboundService()

    async def create_po_v2(
        self,
        session: AsyncSession,
        *,
        supplier: str,
        warehouse_id: int,
        supplier_id: Optional[int] = None,
        supplier_name: Optional[str] = None,
        purchaser: str,
        purchase_time: datetime,
        remark: Optional[str] = None,
        lines: List[Dict[str, Any]],
    ):
        return await _create_po_v2(
            session,
            supplier=supplier,
            warehouse_id=warehouse_id,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            purchaser=purchaser,
            purchase_time=purchase_time,
            remark=remark,
            lines=lines,
        )

    async def get_po_with_lines(
        self,
        session: AsyncSession,
        po_id: int,
        *,
        for_update: bool = False,
    ) -> Optional[PurchaseOrderWithLinesOut]:
        po = await _get_po_with_lines(session, po_id, for_update=for_update)
        if po is None:
            return None

        item_ids = sorted({int(ln.item_id) for ln in (po.lines or []) if ln.item_id})
        items_map = await _load_items_map(session, item_ids)
        barcode_map = await _load_primary_barcodes(session, item_ids)

        out_lines: List[PurchaseOrderLineOut] = []
        for ln in (po.lines or []):
            # ✅ 不能对 ORM 直接 model_validate（因为 qty_remaining_* 是计算字段）

            ordered_purchase = int(getattr(ln, "qty_ordered", 0) or 0)
            upc = _safe_upc(getattr(ln, "units_per_case", None))

            # ✅ base 事实口径
            ordered_base = _get_qty_ordered_base(ln)
            received_base = _get_qty_received_base(ln)
            remaining_base = max(0, ordered_base - received_base)

            # ✅ 采购单位展示口径（由 base 换算，不再把 base 塞进 qty_received）
            received_purchase = _base_to_purchase(received_base, upc)
            remaining_purchase = max(0, ordered_purchase - received_purchase)

            data: Dict[str, Any] = {
                "id": int(getattr(ln, "id")),
                "po_id": int(getattr(ln, "po_id")),
                "line_no": int(getattr(ln, "line_no")),
                "item_id": int(getattr(ln, "item_id")),
                "item_name": getattr(ln, "item_name", None),
                "item_sku": getattr(ln, "item_sku", None),
                "biz_category": getattr(ln, "category", None),
                "spec_text": getattr(ln, "spec_text", None),
                "base_uom": getattr(ln, "base_uom", None),
                "purchase_uom": getattr(ln, "purchase_uom", None),
                "supply_price": getattr(ln, "supply_price", None),
                "retail_price": getattr(ln, "retail_price", None),
                "promo_price": getattr(ln, "promo_price", None),
                "min_price": getattr(ln, "min_price", None),
                "qty_cases": getattr(ln, "qty_cases", None),
                "units_per_case": getattr(ln, "units_per_case", None),

                # 展示：采购单位订购量（输入快照）
                "qty_ordered": ordered_purchase,

                # ✅ base：订购/已收/剩余（唯一真相）
                "qty_ordered_base": ordered_base,
                "qty_received_base": received_base,
                "qty_remaining_base": remaining_base,

                # 兼容展示字段：采购单位口径
                "qty_received": received_purchase,
                "qty_remaining": remaining_purchase,

                "line_amount": getattr(ln, "line_amount", None),
                "status": getattr(ln, "status", None),
                "remark": getattr(ln, "remark", None),
                "created_at": getattr(ln, "created_at"),
                "updated_at": getattr(ln, "updated_at"),

                # Optional 主数据字段先给 None，后面补齐
                "sku": None,
                "primary_barcode": None,
                "brand": None,
                "category": None,
                "supplier_id": None,
                "supplier_name": None,
                "weight_kg": None,
                "uom": None,
                "has_shelf_life": None,
                "shelf_life_value": None,
                "shelf_life_unit": None,
                "enabled": None,
            }

            it = items_map.get(int(getattr(ln, "item_id")))
            if it is not None:
                data["sku"] = it.sku
                data["brand"] = it.brand
                data["category"] = it.category
                data["supplier_id"] = it.supplier_id
                data["supplier_name"] = it.supplier_name
                data["weight_kg"] = getattr(it, "weight_kg", None)
                data["uom"] = it.uom
                data["has_shelf_life"] = it.has_shelf_life
                data["shelf_life_value"] = it.shelf_life_value
                data["shelf_life_unit"] = it.shelf_life_unit
                data["enabled"] = it.enabled

            data["primary_barcode"] = barcode_map.get(int(getattr(ln, "item_id")))

            out_lines.append(PurchaseOrderLineOut.model_validate(data))

        return PurchaseOrderWithLinesOut(
            id=po.id,
            supplier=po.supplier,
            warehouse_id=po.warehouse_id,
            supplier_id=po.supplier_id,
            supplier_name=po.supplier_name,
            total_amount=po.total_amount,
            purchaser=po.purchaser,
            purchase_time=po.purchase_time,
            remark=po.remark,
            status=po.status,
            created_at=po.created_at,
            updated_at=po.updated_at,
            last_received_at=po.last_received_at,
            closed_at=po.closed_at,
            lines=out_lines,
        )

    async def receive_po_line(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        line_id: Optional[int] = None,
        line_no: Optional[int] = None,
        qty: int,
        occurred_at: Optional[datetime] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
    ):
        return await _receive_po_line(
            self.inbound_svc,
            session,
            po_id=po_id,
            line_id=line_id,
            line_no=line_no,
            qty=qty,
            occurred_at=occurred_at,
            production_date=production_date,
            expiry_date=expiry_date,
        )
