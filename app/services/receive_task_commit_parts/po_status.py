# app/services/receive_task_commit_parts/po_status.py
from __future__ import annotations

from datetime import datetime

from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine


def ordered_base(line: PurchaseOrderLine) -> int:
    """
    ✅ Phase 2 冻结前提：ordered 的唯一事实口径是 qty_ordered_base
    services 层不允许出现散落乘法。
    """
    v = getattr(line, "qty_ordered_base", None)
    return int(v or 0)


def received_base(line: PurchaseOrderLine) -> int:
    return int(line.qty_received or 0)


def recalc_po_line_status(line: PurchaseOrderLine) -> None:
    """
    采购行状态推进（✅ base 口径）
    """
    o = ordered_base(line)
    r = received_base(line)
    if r <= 0:
        line.status = "CREATED"
    elif r < o:
        line.status = "PARTIAL"
    else:
        line.status = "RECEIVED"


def recalc_po_header(po: PurchaseOrder, now: datetime) -> None:
    """
    采购单头状态推进（✅ base 口径）
    - all_zero  -> CREATED
    - all_full  -> RECEIVED (+ closed_at)
    - otherwise -> PARTIAL
    并更新 last_received_at / updated_at
    """
    lines = list(po.lines or [])
    all_zero = all(received_base(line) == 0 for line in lines)
    all_full = all(received_base(line) >= ordered_base(line) for line in lines)

    if all_zero:
        po.status = "CREATED"
        po.closed_at = None
    elif all_full:
        po.status = "RECEIVED"
        po.closed_at = now
    else:
        po.status = "PARTIAL"
        po.closed_at = None

    po.last_received_at = now
    po.updated_at = now
