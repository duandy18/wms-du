# app/wms/procurement/services/purchase_order_create.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.models.supplier import Supplier
from app.pms.public.items.contracts.item_basic import ItemBasic
from app.pms.public.items.services.item_read_service import ItemReadService


async def _load_items_map(session: AsyncSession, item_ids: List[int]) -> Dict[int, ItemBasic]:
    if not item_ids:
        return {}
    svc = ItemReadService(session)
    return await svc.aget_basics_by_item_ids(item_ids=item_ids)


async def _require_supplier_for_po(session: AsyncSession, supplier_id: Optional[int]) -> Supplier:
    if supplier_id is None:
        raise ValueError("supplier_id 不能为空：采购单必须绑定供应商")
    sid = int(supplier_id)
    if sid <= 0:
        raise ValueError("supplier_id 非法：采购单必须绑定供应商")

    supplier = ((await session.execute(select(Supplier).where(Supplier.id == sid))).scalars().first())
    if supplier is None:
        raise ValueError(f"supplier_id 不存在：未找到供应商（supplier_id={sid})")

    return supplier


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


async def _require_item_uom_ratio_to_base(
    session: AsyncSession,
    *,
    item_id: int,
    uom_id: int,
) -> int:
    row = await session.execute(
        text(
            """
            SELECT ratio_to_base
            FROM item_uoms
            WHERE id = :uom_id AND item_id = :item_id
            """
        ),
        {"uom_id": int(uom_id), "item_id": int(item_id)},
    )
    r = row.mappings().first()
    if r is None:
        raise ValueError(f"uom_id 不存在或不属于该商品：item_id={int(item_id)} uom_id={int(uom_id)}")

    ratio = int(r.get("ratio_to_base") or 0)
    if ratio <= 0:
        raise ValueError("item_uoms.ratio_to_base 必须 >= 1")

    return ratio


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


async def _pick_default_purchase_uom(session: AsyncSession, *, item_id: int) -> Tuple[int, int]:
    """
    Choose a deterministic purchase uom for an item (unit governance phase 2):
    1) is_purchase_default = true
    2) is_base = true
    3) smallest id (any)
    Returns: (uom_id, ratio_to_base)
    """
    r1 = await session.execute(
        text(
            """
            SELECT id, ratio_to_base
              FROM item_uoms
             WHERE item_id = :i AND is_purchase_default = true
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    m1 = r1.mappings().first()
    if m1 is not None:
        return int(m1["id"]), int(m1["ratio_to_base"])

    r2 = await session.execute(
        text(
            """
            SELECT id, ratio_to_base
              FROM item_uoms
             WHERE item_id = :i AND is_base = true
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    m2 = r2.mappings().first()
    if m2 is not None:
        return int(m2["id"]), int(m2["ratio_to_base"])

    r3 = await session.execute(
        text(
            """
            SELECT id, ratio_to_base
              FROM item_uoms
             WHERE item_id = :i
             ORDER BY id
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    m3 = r3.mappings().first()
    if m3 is not None:
        return int(m3["id"]), int(m3["ratio_to_base"])

    raise ValueError(f"商品缺少 item_uoms：item_id={int(item_id)}")


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

    supplier_obj = await _require_supplier_for_po(session, supplier_id)
    po_supplier_id = int(getattr(supplier_obj, "id"))
    po_supplier_name = str(getattr(supplier_obj, "name") or "").strip()

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
            uom_id, ratio_to_base = await _pick_default_purchase_uom(session, item_id=item_id)
        else:
            ratio_to_base = await _require_item_uom_ratio_to_base(session, item_id=item_id, uom_id=uom_id)

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
                "remark": raw.get("remark"),
            }
        )

    po = PurchaseOrder(
        supplier_id=po_supplier_id,
        supplier_name=po_supplier_name,
        warehouse_id=warehouse_id,
        purchaser=purchaser.strip(),
        purchase_time=purchase_time,
        total_amount=total_amount,
        status="CREATED",
        remark=remark,
    )
    session.add(po)
    await session.flush()

    for nl in norm_lines:
        session.add(PurchaseOrderLine(po_id=po.id, **nl))

    await session.flush()
    return po
