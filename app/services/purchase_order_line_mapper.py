# app/services/purchase_order_line_mapper.py
from __future__ import annotations

from typing import Any, Dict, Tuple

from app.schemas.purchase_order import PurchaseOrderLineOut
from app.services.purchase_order_qty import base_to_purchase, get_qty_ordered_base, get_qty_received_base, safe_upc


def _calc_qty_fields(ln: Any) -> Tuple[int, int, int, int, int, int]:
    """
    返回：
    - ordered_purchase
    - ordered_base
    - received_base
    - remaining_base
    - received_purchase
    - remaining_purchase
    """
    ordered_purchase = int(getattr(ln, "qty_ordered", 0) or 0)
    upc = safe_upc(getattr(ln, "units_per_case", None))

    ordered_base = get_qty_ordered_base(ln)
    received_base = get_qty_received_base(ln)
    remaining_base = max(0, ordered_base - received_base)

    received_purchase = base_to_purchase(received_base, upc)
    remaining_purchase = max(0, ordered_purchase - received_purchase)

    return (
        ordered_purchase,
        ordered_base,
        received_base,
        remaining_base,
        received_purchase,
        remaining_purchase,
    )


def build_line_base_data(ln: Any) -> Dict[str, Any]:
    """
    只负责“行本体 + qty 口径”字段，完全不依赖 items_map/barcode_map。
    """
    (
        ordered_purchase,
        ordered_base,
        received_base,
        remaining_base,
        received_purchase,
        remaining_purchase,
    ) = _calc_qty_fields(ln)

    item_id = int(getattr(ln, "item_id"))

    return {
        "id": int(getattr(ln, "id")),
        "po_id": int(getattr(ln, "po_id")),
        "line_no": int(getattr(ln, "line_no")),
        "item_id": item_id,
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
        "qty_ordered": ordered_purchase,
        "qty_ordered_base": ordered_base,
        "qty_received_base": received_base,
        "qty_remaining_base": remaining_base,
        "qty_received": received_purchase,
        "qty_remaining": remaining_purchase,
        "line_amount": getattr(ln, "line_amount", None),
        "status": getattr(ln, "status", None),
        "remark": getattr(ln, "remark", None),
        "created_at": getattr(ln, "created_at"),
        "updated_at": getattr(ln, "updated_at"),
        # enrich 占位（由 apply_* 补齐）
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


def apply_item_enrichment(data: Dict[str, Any], *, item_obj: Any | None) -> None:
    """
    注入 item 扩展字段（允许 item_obj=None）。
    """
    if item_obj is None:
        return

    data["sku"] = getattr(item_obj, "sku", None)
    data["brand"] = getattr(item_obj, "brand", None)
    data["category"] = getattr(item_obj, "category", None)
    data["supplier_id"] = getattr(item_obj, "supplier_id", None)
    data["supplier_name"] = getattr(item_obj, "supplier_name", None)
    data["weight_kg"] = getattr(item_obj, "weight_kg", None)
    data["uom"] = getattr(item_obj, "uom", None)
    data["has_shelf_life"] = getattr(item_obj, "has_shelf_life", None)
    data["shelf_life_value"] = getattr(item_obj, "shelf_life_value", None)
    data["shelf_life_unit"] = getattr(item_obj, "shelf_life_unit", None)
    data["enabled"] = getattr(item_obj, "enabled", None)


def apply_barcode_enrichment(data: Dict[str, Any], *, primary_barcode: str | None) -> None:
    """
    注入条码扩展字段（允许 primary_barcode=None）。
    """
    data["primary_barcode"] = primary_barcode


def map_po_line_out(
    ln: Any,
    *,
    items_map: Dict[int, Any],
    barcode_map: Dict[int, str],
) -> PurchaseOrderLineOut:
    """
    单行映射（可扩展但不污染 presenter/service）：
    - build_line_base_data：行本体 + qty
    - apply_item_enrichment：item 扩展
    - apply_barcode_enrichment：条码扩展
    """
    data = build_line_base_data(ln)
    item_id = int(data["item_id"])

    apply_item_enrichment(data, item_obj=items_map.get(item_id))
    apply_barcode_enrichment(data, primary_barcode=barcode_map.get(item_id))

    return PurchaseOrderLineOut.model_validate(data)
