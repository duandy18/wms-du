# app/services/purchase_order_receive_workbench.py
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.purchase_order_receive_workbench import (
    PurchaseOrderReceiveWorkbenchOut,
    WorkbenchCapsOut,
    WorkbenchExplainOut,
    WorkbenchRowOut,
)
from app.services.purchase_order_queries import get_po_with_lines
from app.services.qty_base import ordered_base as _ordered_base_impl

from .purchase_order_receive_workbench_builder import (
    build_po_summary,
    build_receipt_summary,
    merge_batches,
    ordered_base,
    sort_batches,
    sort_rows,
)
from .purchase_order_receive_workbench_canon import fill_canonical_batch_dates
from .purchase_order_receive_workbench_queries import (
    build_draft_received_aggregates,
    load_latest_po_draft_receipt_with_lines,
    load_po_confirmed_batches_map,
    load_po_confirmed_received_map,
)
from app.services.inbound_receipt_explain import explain_receipt


async def get_receive_workbench(session: AsyncSession, *, po_id: int) -> PurchaseOrderReceiveWorkbenchOut:
    po = await get_po_with_lines(session, int(po_id), for_update=False)
    if po is None:
        raise ValueError(f"PurchaseOrder not found: id={po_id}")

    po_summary = build_po_summary(po)

    draft = await load_latest_po_draft_receipt_with_lines(session, po_id=int(po.id))

    confirmed_map = await load_po_confirmed_received_map(session, po_id=int(po.id))
    confirmed_batches_map = await load_po_confirmed_batches_map(session, po_id=int(po.id))

    draft_map, draft_batches_map = build_draft_received_aggregates(draft=draft)

    # 没有行：直接返回（保持原行为）
    if not getattr(po, "lines", None):
        caps = WorkbenchCapsOut(
            can_confirm=False,
            can_start_draft=True,
            receipt_id=int(draft.id) if draft is not None else None,
        )
        return PurchaseOrderReceiveWorkbenchOut(
            po_summary=po_summary,
            receipt=build_receipt_summary(draft) if draft is not None else None,
            rows=[],
            explain=None,
            caps=caps,
        )

    # ✅ canonical 日期回填：从 batches 取 production/expiry
    po_line_to_item_id: Dict[int, int] = {
        int(getattr(ln, "id")): int(getattr(ln, "item_id")) for ln in (po.lines or [])
    }
    wh_id = int(getattr(po, "warehouse_id"))

    await fill_canonical_batch_dates(
        session,
        warehouse_id=wh_id,
        po_line_to_item_id=po_line_to_item_id,
        batches_map=confirmed_batches_map,
    )
    await fill_canonical_batch_dates(
        session,
        warehouse_id=wh_id,
        po_line_to_item_id=po_line_to_item_id,
        batches_map=draft_batches_map,
    )

    # 回填后统一排序
    for xs in confirmed_batches_map.values():
        sort_batches(xs)
    for xs in draft_batches_map.values():
        sort_batches(xs)

    rows: List[WorkbenchRowOut] = []
    for line in po.lines:
        po_line_id = int(getattr(line, "id"))
        ordered_qty = ordered_base(line, _ordered_base_impl)

        confirmed_received = int(confirmed_map.get(po_line_id, 0))
        draft_received = int(draft_map.get(po_line_id, 0))
        remaining = max(int(ordered_qty) - int(confirmed_received) - int(draft_received), 0)

        draft_batches = draft_batches_map.get(po_line_id, [])
        confirmed_batches = confirmed_batches_map.get(po_line_id, [])
        all_batches = merge_batches(confirmed=confirmed_batches, draft=draft_batches)

        rows.append(
            WorkbenchRowOut(
                po_line_id=po_line_id,
                line_no=int(getattr(line, "line_no", 0) or 0),
                item_id=int(getattr(line, "item_id")),
                item_name=getattr(line, "item_name", None),
                item_sku=getattr(line, "item_sku", None),
                ordered_qty=int(ordered_qty),
                confirmed_received_qty=int(confirmed_received),
                draft_received_qty=int(draft_received),
                remaining_qty=int(remaining),
                batches=draft_batches,
                confirmed_batches=confirmed_batches,
                all_batches=all_batches,
            )
        )

    sort_rows(rows)

    explain_out: Optional[WorkbenchExplainOut] = None
    can_confirm = False
    receipt_summary = None

    if draft is not None:
        receipt_summary = build_receipt_summary(draft)
        exp = await explain_receipt(session=session, receipt=draft)
        can_confirm = bool(exp.confirmable)
        explain_out = WorkbenchExplainOut(
            confirmable=bool(exp.confirmable),
            blocking_errors=[e.model_dump() for e in exp.blocking_errors],
            normalized_lines_preview=[x.model_dump() for x in exp.normalized_lines_preview],
        )

    caps = WorkbenchCapsOut(
        can_confirm=bool(can_confirm),
        can_start_draft=True,
        receipt_id=int(draft.id) if draft is not None else None,
    )

    return PurchaseOrderReceiveWorkbenchOut(
        po_summary=po_summary,
        receipt=receipt_summary,
        rows=rows,
        explain=explain_out,
        caps=caps,
    )
