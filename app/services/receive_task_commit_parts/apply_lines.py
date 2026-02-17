# app/services/receive_task_commit_parts/apply_lines.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_receipt import InboundReceipt
from app.models.purchase_order_line import PurchaseOrderLine
from app.models.receive_task import ReceiveTask
from app.services.inbound_service import InboundService
from app.services.receive_task_commit_parts.apply_inbound_effect import apply_inbound_and_collect_effect
from app.services.receive_task_commit_parts.apply_receipt_facts import ensure_receipt_and_add_line
from app.services.receive_task_commit_parts.po_status import recalc_po_line_status


async def apply_task_lines(
    session: AsyncSession,
    *,
    inbound_svc: InboundService,
    task: ReceiveTask,
    po_lines_map: dict[int, PurchaseOrderLine],
    ref: str,
    sub_reason: str,
    trace_id: Optional[str],
    now: datetime,
) -> Tuple[Optional[InboundReceipt], int, List[Dict[str, Any]], dict[int, int], bool]:
    """
    逐行执行 commit 主线（编排层）：
    - 核算主线：写库存/台账（inbound_svc.receive）+ 收集 effects
    - PO 回写：qty_received += base（命中 po_line 时）
    - 凭证事实：写 InboundReceipt / InboundReceiptLine（仅凭证，不影响核算）
    - 统计 ORDER 退货汇总 returned_by_item

    返回：
    - receipt（可能为 None：本次所有 scanned_qty=0）
    - ref_line_counter
    - effects（用于三账一致性验证）
    - returned_by_item
    - touched_po_qty
    """
    receipt: Optional[InboundReceipt] = None
    ref_line_counter = 0
    returned_by_item: dict[int, int] = {}
    effects: List[Dict[str, Any]] = []
    touched_po_qty = False

    for line in task.lines or []:
        if line.scanned_qty == 0:
            line.committed_qty = 0
            line.status = "COMMITTED"
            continue

        qty_base = int(line.scanned_qty)
        if qty_base <= 0:
            line.committed_qty = 0
            line.status = "COMMITTED"
            continue

        line.committed_qty = qty_base
        ref_line_counter += 1

        # 1) 核算主线：写库存/台账 + 收集 effect
        upc, effect = await apply_inbound_and_collect_effect(
            session,
            inbound_svc=inbound_svc,
            warehouse_id=int(task.warehouse_id),
            item_id=int(line.item_id),
            units_per_case=getattr(line, "units_per_case", None),
            batch_code=line.batch_code,
            production_date=line.production_date,
            expiry_date=line.expiry_date,
            qty_base=int(qty_base),
            ref=str(ref),
            ref_line=int(ref_line_counter),
            trace_id=trace_id,
            sub_reason=str(sub_reason),
            now=now,
        )
        effects.append(effect)

        line.status = "COMMITTED"

        # 2) 回写 PO 行：qty_received += base
        po_line: Optional[PurchaseOrderLine] = None
        if line.po_line_id is not None and line.po_line_id in po_lines_map:
            po_line = po_lines_map[line.po_line_id]
            po_line.qty_received = int(po_line.qty_received or 0) + int(qty_base)
            recalc_po_line_status(po_line)
            touched_po_qty = True

        # 3) 凭证事实层：receipt header/line
        receipt, _created = await ensure_receipt_and_add_line(
            session,
            task=task,
            receipt=receipt,
            ref=str(ref),
            trace_id=trace_id,
            now=now,
            ref_line=int(ref_line_counter),
            qty_base=int(qty_base),
            upc=int(upc),
            task_line=line,
            po_line=po_line,
        )

        if task.source_type == "ORDER":
            returned_by_item[int(line.item_id)] = returned_by_item.get(int(line.item_id), 0) + int(qty_base)

    return receipt, ref_line_counter, effects, returned_by_item, touched_po_qty
