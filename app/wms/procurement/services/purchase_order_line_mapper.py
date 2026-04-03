# app/wms/procurement/services/purchase_order_line_mapper.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from app.wms.procurement.contracts.purchase_order import PurchaseOrderLineListOut
from app.wms.procurement.services.purchase_order_qty import get_qty_ordered_base


def _safe_int(v: object, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def build_line_base_data(*, ln: Any, received_base: int) -> Dict[str, Any]:
    ordered_base = get_qty_ordered_base(ln)
    received_base_i = max(_safe_int(received_base or 0, 0), 0)
    remaining_base = max(0, ordered_base - received_base_i)

    discount_amount = getattr(ln, "discount_amount", None)
    try:
        discount_amount_val = Decimal(str(discount_amount or 0))
    except Exception:
        discount_amount_val = Decimal("0")

    return {
        "id": _safe_int(getattr(ln, "id"), 0),
        "po_id": _safe_int(getattr(ln, "po_id"), 0),
        "line_no": _safe_int(getattr(ln, "line_no"), 0),
        "item_id": _safe_int(getattr(ln, "item_id"), 0),
        "item_name": getattr(ln, "item_name", None),
        "item_sku": getattr(ln, "item_sku", None),
        "spec_text": getattr(ln, "spec_text", None),
        "supply_price": getattr(ln, "supply_price", None),
        "discount_amount": discount_amount_val,
        "discount_note": getattr(ln, "discount_note", None),
        "qty_ordered_input": getattr(ln, "qty_ordered_input", 0),
        "purchase_ratio_to_base_snapshot": getattr(
            ln, "purchase_ratio_to_base_snapshot", 1
        ),
        "qty_ordered_base": ordered_base,
        "qty_received_base": received_base_i,
        "qty_remaining_base": remaining_base,
        "remark": getattr(ln, "remark", None),
        "created_at": getattr(ln, "created_at"),
        "updated_at": getattr(ln, "updated_at"),
    }


def map_po_line_out(
    ln: Any,
    *,
    received_base: int,
    items_map: Dict[int, Any],
    barcode_map: Dict[int, str],
) -> PurchaseOrderLineListOut:
    data = build_line_base_data(ln=ln, received_base=received_base)
    return PurchaseOrderLineListOut.model_validate(data)
