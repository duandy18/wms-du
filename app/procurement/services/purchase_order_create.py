# app/procurement/services/purchase_order_create.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.models.purchase_order import PurchaseOrder
from app.pms.public.items.contracts.item_basic import ItemBasic
from app.pms.public.items.services.item_read_service import ItemReadService
from app.pms.public.suppliers.services.supplier_read_service import SupplierReadService
from app.procurement.repos.purchase_order_create_repo import (
    insert_purchase_order_head,
    insert_purchase_order_lines,
    pick_default_purchase_uom,
    require_item_uom_ratio_to_base,
    reserve_purchase_order_id,
)


async def _load_items_map(session: AsyncSession, item_ids: List[int]) -> Dict[int, ItemBasic]:
    if not item_ids:
        return {}
    svc = ItemReadService(session)
    return await svc.aget_basics_by_item_ids(item_ids=item_ids)


async def _require_supplier_snapshot_via_pms(
    session: AsyncSession,
    supplier_id: Optional[int],
) -> Tuple[int, str]:
    """
    供应商真相直接来自 PMS public/service。
    返回：
    - supplier_id
    - supplier_name（用于 PO 快照）
    """
    if supplier_id is None:
        raise ValueError("supplier_id 不能为空：采购单必须绑定供应商")

    sid = int(supplier_id)
    if sid <= 0:
        raise ValueError("supplier_id 非法：采购单必须绑定供应商")

    svc = SupplierReadService(session)
    supplier = await svc.aget_basic_by_id(supplier_id=sid)
    if supplier is None:
        raise ValueError(f"supplier_id 不存在：未找到供应商（supplier_id={sid}）")

    return int(supplier.id), str(supplier.name).strip()


def _trim_or_none(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _parse_discount_amount(v: Any) -> Decimal:
    if v is None or (isinstance(v, str) and not v.strip()):
        return Decimal("0")
    try:
        d = Decimal(str(v))
    except Exception as e:
        raise ValueError("discount_amount 必须为数字") from e
    if d < 0:
        raise ValueError("discount_amount 必须 >= 0")
    return d


def _require_qty_input_from_raw(raw: Dict[str, Any]) -> int:
    """
    PO line contract (Phase M-5+):
    - preferred: qty_input
    - legacy fallback: qty / qty_ordered
    """
    v = raw.get("qty_input", raw.get("qty", raw.get("qty_ordered")))
    if v is None:
        raise KeyError("qty_input")
    return int(v)


def _maybe_uom_id_from_raw(raw: Dict[str, Any]) -> Optional[int]:
    """
    PO line contract (Phase M-5+):
    - preferred: uom_id
    - tolerate common legacy keys (input layer only)
    """
    v = raw.get("uom_id", raw.get("purchase_uom_id", raw.get("purchase_uom_id_snapshot")))
    if v is None:
        return None
    return int(v)


def _build_po_no(*, po_id: int) -> str:
    return f"PO-{int(po_id)}"


async def create_po_v2(
    session: AsyncSession,
    *,
    supplier_id: int,
    warehouse_id: int,
    purchaser: str,
    purchase_time: datetime,
    remark: Optional[str] = None,
    lines: List[Dict[str, Any]],
) -> PurchaseOrder:
    if not lines:
        raise ValueError("create_po_v2 需要至少一行行项目（lines 不可为空）")

    purchaser_text = (purchaser or "").strip()
    if not purchaser_text:
        raise ValueError("purchaser 不能为空：采购单必须填写采购人")

    po_supplier_id, po_supplier_name = await _require_supplier_snapshot_via_pms(
        session,
        supplier_id,
    )

    raw_item_ids = [int(raw["item_id"]) for raw in lines]
    items_map = await _load_items_map(session, raw_item_ids)

    norm_lines: List[Dict[str, Any]] = []
    total_amount = Decimal("0")

    for idx, raw in enumerate(lines, start=1):
        item_id = int(raw["item_id"])
        qty_input = _require_qty_input_from_raw(raw)

        it = items_map.get(item_id)
        if it is None:
            raise ValueError(f"商品不存在：item_id={int(item_id)}")

        it_supplier_id = int(it.supplier_id or 0)
        if it_supplier_id != 0 and it_supplier_id != po_supplier_id:
            raise ValueError("商品不属于当前供应商")

        uom_id = _maybe_uom_id_from_raw(raw)
        if uom_id is None:
            uom_id, ratio_to_base = await pick_default_purchase_uom(session, item_id=item_id)
        else:
            ratio_to_base = await require_item_uom_ratio_to_base(
                session,
                item_id=item_id,
                uom_id=uom_id,
            )

        qty_ordered_base = qty_input * ratio_to_base
        if qty_ordered_base <= 0:
            raise ValueError("行 qty_ordered_base 必须 > 0")

        supply_price = raw.get("supply_price")
        if supply_price is not None:
            supply_price = Decimal(str(supply_price))

        discount_amount = _parse_discount_amount(raw.get("discount_amount"))
        line_total = (
            (Decimal("0") if supply_price is None else (supply_price * Decimal(qty_ordered_base)))
            - discount_amount
        )
        total_amount += line_total

        norm_lines.append(
            {
                "line_no": raw.get("line_no") or idx,
                "item_id": item_id,
                "item_name": it.name,
                "item_sku": it.sku,
                "spec_text": raw.get("spec_text"),
                "purchase_uom_id_snapshot": uom_id,
                "purchase_ratio_to_base_snapshot": ratio_to_base,
                "qty_ordered_input": qty_input,
                "qty_ordered_base": qty_ordered_base,
                "supply_price": supply_price,
                "discount_amount": discount_amount,
                "discount_note": raw.get("discount_note"),
                "remark": _trim_or_none(raw.get("remark")),
            }
        )

    po_id = await reserve_purchase_order_id(session)
    po_no = _build_po_no(po_id=po_id)

    po = await insert_purchase_order_head(
        session,
        po_id=po_id,
        po_no=po_no,
        supplier_id=po_supplier_id,
        supplier_name=po_supplier_name,
        warehouse_id=int(warehouse_id),
        purchaser=purchaser_text,
        purchase_time=purchase_time,
        total_amount=total_amount,
        remark=_trim_or_none(remark),
    )

    await insert_purchase_order_lines(
        session,
        po_id=int(po.id),
        lines=norm_lines,
    )

    return po
