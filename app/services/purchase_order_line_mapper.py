# app/services/purchase_order_line_mapper.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from app.schemas.purchase_order import PurchaseOrderLineOut
from app.services.purchase_order_qty import get_qty_ordered_base


def _safe_int(v: object, default: int) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except Exception:
        return default


def _safe_case_ratio_snapshot(ln: Any) -> int:
    """
    Phase2：倍率快照（1 采购单位 = 多少最小单位）
    - 优先 case_ratio_snapshot
    - 兜底为 1（避免除零/异常）
    """
    ratio = getattr(ln, "case_ratio_snapshot", None)
    r = _safe_int(ratio, 0)
    return r if r > 0 else 1


def build_line_base_data(*, ln: Any, received_base: int) -> Dict[str, Any]:
    """
    只负责“行本体 + 执行口径（base）”字段（已收来自 receipt 聚合注入）。

    Phase2 对外契约升级后：
    - 不再输出 qty_ordered / units_per_case / purchase_uom 等旧字段
    - 不再输出采购口径 qty_received/qty_remaining（展示/兼容口径）
    """
    ordered_base = get_qty_ordered_base(ln)
    received_base_i = max(_safe_int(received_base or 0, 0), 0)
    remaining_base = max(0, ordered_base - received_base_i)

    item_id = _safe_int(getattr(ln, "item_id"), 0)

    discount_amount = getattr(ln, "discount_amount", None)
    try:
        discount_amount_val = Decimal(str(discount_amount or 0))
    except Exception:
        discount_amount_val = Decimal("0")

    return {
        "id": _safe_int(getattr(ln, "id"), 0),
        "po_id": _safe_int(getattr(ln, "po_id"), 0),
        "line_no": _safe_int(getattr(ln, "line_no"), 0),
        "item_id": item_id,
        "item_name": getattr(ln, "item_name", None),
        "item_sku": getattr(ln, "item_sku", None),
        "spec_text": getattr(ln, "spec_text", None),
        "base_uom": getattr(ln, "base_uom", None),
        "supply_price": getattr(ln, "supply_price", None),
        "discount_amount": discount_amount_val,
        "discount_note": getattr(ln, "discount_note", None),
        # ✅ 快照解释器（Phase2 合同，第一公民）
        "uom_snapshot": getattr(ln, "uom_snapshot", None),
        "case_ratio_snapshot": getattr(ln, "case_ratio_snapshot", None),
        "case_uom_snapshot": getattr(ln, "case_uom_snapshot", None),
        "qty_ordered_case_input": getattr(ln, "qty_ordered_case_input", None),
        # ✅ 事实/执行口径（base）
        "qty_ordered_base": ordered_base,
        "qty_received_base": received_base_i,
        "qty_remaining_base": remaining_base,
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
    received_base: int,
    items_map: Dict[int, Any],
    barcode_map: Dict[int, str],
) -> PurchaseOrderLineOut:
    """
    单行映射：
    - build_line_base_data：行本体 + qty（已收来自 receipt 聚合注入）
    - apply_item_enrichment：item 扩展
    - apply_barcode_enrichment：条码扩展
    """
    data = build_line_base_data(ln=ln, received_base=received_base)
    item_id = int(data["item_id"])

    apply_item_enrichment(data, item_obj=items_map.get(item_id))
    apply_barcode_enrichment(data, primary_barcode=barcode_map.get(item_id))

    return PurchaseOrderLineOut.model_validate(data)
