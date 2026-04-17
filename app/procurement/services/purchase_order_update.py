# app/procurement/services/purchase_order_update.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.models.purchase_order import PurchaseOrder
from app.pms.public.items.contracts.item_basic import ItemBasic
from app.procurement.repos.purchase_order_create_repo import (
    pick_default_purchase_uom,
    require_item_uom_ratio_to_base,
)
from app.procurement.repos.purchase_order_line_completion_repo import (
    rebuild_completion_rows_for_po,
)
from app.procurement.repos.purchase_order_queries_repo import get_po_with_lines
from app.procurement.repos.purchase_order_update_repo import (
    has_po_committed_inbound_facts,
    has_po_confirmed_receipt,
    replace_purchase_order_lines,
)
from app.procurement.services.purchase_order_create import (
    _load_items_map,
    _maybe_uom_id_from_raw,
    _parse_discount_amount,
    _require_qty_input_from_raw,
    _require_supplier_snapshot_via_pms,
    _trim_or_none,
)


def _normalize_purchaser_text(v: str) -> str:
    s = (v or "").strip()
    if not s:
        raise ValueError("purchaser 不能为空：采购单必须填写采购人")
    return s


async def _normalize_update_payload(
    session: AsyncSession,
    *,
    supplier_id: int,
    purchaser: str,
    lines: List[Dict[str, Any]],
) -> Tuple[int, str, str, Decimal, List[Dict[str, Any]]]:
    if not lines:
        raise ValueError("update_po_v2 需要至少一行行项目（lines 不可为空）")

    purchaser_text = _normalize_purchaser_text(purchaser)

    po_supplier_id, po_supplier_name = await _require_supplier_snapshot_via_pms(
        session,
        supplier_id,
    )

    raw_item_ids = [int(raw["item_id"]) for raw in lines]
    items_map: Dict[int, ItemBasic] = await _load_items_map(session, raw_item_ids)

    norm_lines: List[Dict[str, Any]] = []
    total_amount = Decimal("0")
    seen_line_nos: set[int] = set()

    for idx, raw in enumerate(lines, start=1):
        line_no = int(raw.get("line_no") or idx)
        if line_no <= 0:
            raise ValueError("line_no 必须 > 0")
        if line_no in seen_line_nos:
            raise ValueError(f"line_no 重复：{line_no}")
        seen_line_nos.add(line_no)

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
            (
                uom_id,
                ratio_to_base,
                purchase_uom_name_snapshot,
            ) = await pick_default_purchase_uom(session, item_id=item_id)
        else:
            ratio_to_base, purchase_uom_name_snapshot = await require_item_uom_ratio_to_base(
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
                "line_no": int(line_no),
                "item_id": item_id,
                "item_name": it.name,
                "item_sku": it.sku,
                "spec_text": raw.get("spec_text"),
                "purchase_uom_id_snapshot": int(uom_id),
                "purchase_uom_name_snapshot": purchase_uom_name_snapshot,
                "purchase_ratio_to_base_snapshot": int(ratio_to_base),
                "qty_ordered_input": int(qty_input),
                "qty_ordered_base": int(qty_ordered_base),
                "supply_price": supply_price,
                "discount_amount": discount_amount,
                "discount_note": raw.get("discount_note"),
                "remark": _trim_or_none(raw.get("remark")),
            }
        )

    return po_supplier_id, po_supplier_name, purchaser_text, total_amount, norm_lines


async def _require_po_editable(
    session: AsyncSession,
    *,
    po: PurchaseOrder,
) -> None:
    st = str(getattr(po, "status", "") or "").upper()
    if st != "CREATED":
        raise HTTPException(status_code=409, detail=f"PO 状态不允许编辑：status={st}")

    po_id = int(getattr(po, "id"))

    if await has_po_confirmed_receipt(session, po_id=po_id):
        raise HTTPException(status_code=409, detail="PO 已存在 CONFIRMED 收货单，禁止编辑")

    if await has_po_committed_inbound_facts(session, po_id=po_id):
        raise HTTPException(status_code=409, detail="PO 已存在正式采购入库事实，禁止编辑")


async def update_po_v2(
    session: AsyncSession,
    *,
    po_id: int,
    supplier_id: int,
    warehouse_id: int,
    purchaser: str,
    purchase_time: datetime,
    remark: str | None = None,
    lines: List[Dict[str, Any]],
) -> PurchaseOrder:
    po = await get_po_with_lines(session, int(po_id), for_update=True)
    if po is None:
        raise HTTPException(status_code=404, detail="PurchaseOrder not found")

    await _require_po_editable(session, po=po)

    (
        po_supplier_id,
        po_supplier_name,
        purchaser_text,
        total_amount,
        norm_lines,
    ) = await _normalize_update_payload(
        session,
        supplier_id=int(supplier_id),
        purchaser=purchaser,
        lines=lines,
    )

    po.supplier_id = int(po_supplier_id)
    po.supplier_name = str(po_supplier_name)
    po.warehouse_id = int(warehouse_id)
    po.purchaser = purchaser_text
    po.purchase_time = purchase_time
    po.total_amount = total_amount
    po.remark = _trim_or_none(remark)

    await session.flush()

    await replace_purchase_order_lines(
        session,
        po_id=int(po.id),
        lines=norm_lines,
    )
    await rebuild_completion_rows_for_po(session, po_id=int(po.id))
    await session.flush()

    try:
        session.expire(po)
    except Exception:
        pass

    return po


__all__ = ["update_po_v2"]
