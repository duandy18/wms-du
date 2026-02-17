# app/services/receive_task_commit_parts/po_loader.py
from __future__ import annotations

from typing import Optional, Tuple

from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.receive_task_loaders import load_po


async def load_po_and_lines_map(
    session,
    *,
    po_id: Optional[int],
) -> Tuple[Optional[PurchaseOrder], dict[int, PurchaseOrderLine]]:
    """
    commit 子流程：如果 task.po_id 存在，则加载 PO（含 lines）并构建 id->line 的 map。
    若 po_id 为空，返回 (None, {}).

    注意：这里保持与现有语义一致：commit 时无需对 PO 加 for_update 锁，
    因为 commit 入口已对 receive_task 加 for_update；
    若后续你要进一步收紧“PO 数量合同”，可在此处升级为 load_po(..., for_update=True)。
    """
    if po_id is None:
        return None, {}

    po = await load_po(session, po_id)
    po_lines_map: dict[int, PurchaseOrderLine] = {}
    for ln in po.lines or []:
        po_lines_map[int(ln.id)] = ln
    return po, po_lines_map
