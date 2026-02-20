# app/services/purchase_order_presenter.py
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.purchase_order import PurchaseOrderWithLinesOut
from app.services.purchase_order_enrichment import load_items_map, load_primary_barcodes
from app.services.purchase_order_line_mapper import map_po_line_out


async def _load_po_confirmed_received_base_map(
    session: AsyncSession, *, po_id: int
) -> Dict[int, int]:
    """
    维度：po_line_id -> sum(qty_received)（仅 CONFIRMED receipts）
    说明：PO 行不再持久化 qty_received，执行口径从 Receipt 事实聚合获得。
    """
    sql = text(
        """
        SELECT rl.po_line_id AS po_line_id,
               COALESCE(SUM(rl.qty_received), 0)::int AS qty
          FROM inbound_receipt_lines rl
          JOIN inbound_receipts r
            ON r.id = rl.receipt_id
         WHERE r.source_type = 'PO'
           AND r.source_id = :po_id
           AND r.status = 'CONFIRMED'
           AND rl.po_line_id IS NOT NULL
         GROUP BY rl.po_line_id
        """
    )
    rows = (await session.execute(sql, {"po_id": int(po_id)})).mappings().all()
    out: Dict[int, int] = {}
    for r in rows:
        pid = int(r.get("po_line_id") or 0)
        if pid > 0:
            out[pid] = int(r.get("qty") or 0)
    return out


async def build_po_with_lines_out(session: AsyncSession, po: Any) -> PurchaseOrderWithLinesOut:
    """
    将 ORM PurchaseOrder（已加载 lines）组装为 PurchaseOrderWithLinesOut。

    职责边界：
    - presenter：组织流程（排序/批量加载/enrich map/已收聚合/组装头部）
    - line_mapper：单行映射（qty 换算 + item/barcode enrich + Pydantic validate）
    """
    if getattr(po, "lines", None):
        po.lines.sort(key=lambda line: (line.line_no, line.id))

    item_ids = sorted({int(ln.item_id) for ln in (po.lines or []) if getattr(ln, "item_id", None)})
    items_map: Dict[int, Any] = await load_items_map(session, item_ids)
    barcode_map = await load_primary_barcodes(session, item_ids)

    received_map = await _load_po_confirmed_received_base_map(session, po_id=int(po.id))

    out_lines: List[Any] = []
    for ln in po.lines or []:
        received_base = int(received_map.get(int(getattr(ln, "id")), 0) or 0)
        out_lines.append(
            map_po_line_out(
                ln,
                received_base=received_base,
                items_map=items_map,
                barcode_map=barcode_map,
            )
        )

    return PurchaseOrderWithLinesOut(
        id=po.id,
        warehouse_id=po.warehouse_id,
        supplier_id=int(getattr(po, "supplier_id")),
        supplier_name=str(getattr(po, "supplier_name") or ""),
        total_amount=getattr(po, "total_amount", None),
        purchaser=po.purchaser,
        purchase_time=po.purchase_time,
        remark=po.remark,
        status=po.status,
        created_at=po.created_at,
        updated_at=po.updated_at,
        last_received_at=po.last_received_at,
        closed_at=po.closed_at,
        # ✅ 关闭/取消审计字段
        close_reason=getattr(po, "close_reason", None),
        close_note=getattr(po, "close_note", None),
        closed_by=getattr(po, "closed_by", None),
        canceled_at=getattr(po, "canceled_at", None),
        canceled_reason=getattr(po, "canceled_reason", None),
        canceled_by=getattr(po, "canceled_by", None),
        lines=out_lines,
    )
