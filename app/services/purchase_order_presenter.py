# app/services/purchase_order_presenter.py
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.purchase_order import PurchaseOrderWithLinesOut
from app.services.purchase_order_enrichment import load_items_map, load_primary_barcodes
from app.services.purchase_order_line_mapper import map_po_line_out


async def build_po_with_lines_out(session: AsyncSession, po: Any) -> PurchaseOrderWithLinesOut:
    """
    将 ORM PurchaseOrder（已加载 lines）组装为 PurchaseOrderWithLinesOut。

    职责边界（拆分后）：
    - presenter：组织流程（排序/批量加载/enrich map/组装头部）
    - line_mapper：单行映射（qty 换算 + item/barcode enrich + Pydantic validate）
    - enrichment：批量加载 items / barcodes
    - service：事务边界 + 必要的 refresh（保证 close 回显与 DB 一致）
    """
    if getattr(po, "lines", None):
        po.lines.sort(key=lambda line: (line.line_no, line.id))

    item_ids = sorted({int(ln.item_id) for ln in (po.lines or []) if getattr(ln, "item_id", None)})
    items_map: Dict[int, Any] = await load_items_map(session, item_ids)
    barcode_map = await load_primary_barcodes(session, item_ids)

    out_lines: List[Any] = []
    for ln in (po.lines or []):
        out_lines.append(
            map_po_line_out(
                ln,
                items_map=items_map,
                barcode_map=barcode_map,
            )
        )

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
        # ✅ 关闭/取消审计字段（保证 close API 回显与 DB 一致）
        close_reason=getattr(po, "close_reason", None),
        close_note=getattr(po, "close_note", None),
        closed_by=getattr(po, "closed_by", None),
        canceled_at=getattr(po, "canceled_at", None),
        canceled_reason=getattr(po, "canceled_reason", None),
        canceled_by=getattr(po, "canceled_by", None),
        lines=out_lines,
    )
