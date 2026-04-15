# app/procurement/services/purchase_order_presenter.py
from __future__ import annotations

from typing import Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.contracts.purchase_order import PurchaseOrderWithLinesOut
from app.procurement.repos.purchase_order_update_repo import (
    has_po_committed_inbound_facts,
    has_po_confirmed_receipt,
    has_po_draft_receipt,
)
from app.procurement.services.purchase_order_line_mapper import map_po_line_out


async def _resolve_po_editability(
    session: AsyncSession,
    po: Any,
) -> tuple[bool, str | None]:
    st = str(getattr(po, "status", "") or "").upper()
    if st != "CREATED":
        return False, f"PO 状态不允许编辑：status={st}"

    po_id = int(getattr(po, "id"))

    if await has_po_draft_receipt(session, po_id=po_id):
        return False, "当前采购单存在 DRAFT 收货单，禁止编辑"

    if await has_po_confirmed_receipt(session, po_id=po_id):
        return False, "当前采购单已存在 CONFIRMED 收货单，禁止编辑"

    if await has_po_committed_inbound_facts(session, po_id=po_id):
        return False, "当前采购单已存在正式采购入库事实，禁止编辑"

    return True, None


async def build_po_with_lines_out(
    session: AsyncSession, po: Any
) -> PurchaseOrderWithLinesOut:
    _ = session

    if getattr(po, "lines", None):
        po.lines.sort(key=lambda line: (line.line_no, line.id))

    out_lines: List[Any] = []
    for ln in po.lines or []:
        out_lines.append(map_po_line_out(ln))

    editable, edit_block_reason = await _resolve_po_editability(session, po)

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
        editable=editable,
        edit_block_reason=edit_block_reason,
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
