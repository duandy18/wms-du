# app/wms/procurement/services/purchase_order_presenter.py
from __future__ import annotations

from typing import Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.contracts.purchase_order import PurchaseOrderWithLinesOut
from app.procurement.services.purchase_order_line_mapper import map_po_line_out


async def build_po_with_lines_out(
    session: AsyncSession, po: Any
) -> PurchaseOrderWithLinesOut:
    _ = session

    if getattr(po, "lines", None):
        po.lines.sort(key=lambda line: (line.line_no, line.id))

    out_lines: List[Any] = []
    for ln in po.lines or []:
        out_lines.append(map_po_line_out(ln))

    return PurchaseOrderWithLinesOut(
        id=po.id,
        po_no=str(getattr(po, "po_no") or ""),
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
        close_reason=getattr(po, "close_reason", None),
        close_note=getattr(po, "close_note", None),
        closed_by=getattr(po, "closed_by", None),
        canceled_at=getattr(po, "canceled_at", None),
        canceled_reason=getattr(po, "canceled_reason", None),
        canceled_by=getattr(po, "canceled_by", None),
        lines=out_lines,
    )
