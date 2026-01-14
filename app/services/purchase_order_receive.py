# app/services/purchase_order_receive.py
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.services.inbound_service import InboundService
from app.services.purchase_order_queries import get_po_with_lines
from app.services.purchase_order_time import UTC


async def receive_po_line(
    inbound_svc: InboundService,
    session: AsyncSession,
    *,
    po_id: int,
    line_id: Optional[int] = None,
    line_no: Optional[int] = None,
    qty: int,
    occurred_at: Optional[datetime] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
) -> PurchaseOrder:
    """
    对某一行执行收货（行级收货）。

    关键合同：
    - stock_ledger 存在唯一约束 (reason, ref, ref_line)
      => ref_line 必须在 (reason, ref) 维度全局递增，不能按 item_id 分桶。
    """
    if qty <= 0:
        raise ValueError("收货数量 qty 必须 > 0")
    if line_id is None and line_no is None:
        raise ValueError("receive_po_line 需要提供 line_id 或 line_no 之一")

    po = await get_po_with_lines(session, po_id, for_update=True)
    if po is None:
        raise ValueError(f"PurchaseOrder not found: id={po_id}")

    if not po.lines:
        raise ValueError(f"采购单 {po_id} 没有任何行，无法执行行级收货")

    target: Optional[PurchaseOrderLine] = None
    if line_id is not None:
        for line in po.lines:
            if line.id == line_id:
                target = line
                break
    elif line_no is not None:
        for line in po.lines:
            if line.line_no == line_no:
                target = line
                break

    if target is None:
        raise ValueError(
            f"在采购单 {po_id} 中未找到匹配的行 (line_id={line_id}, line_no={line_no})"
        )

    if target.status in {"RECEIVED", "CLOSED"}:
        raise ValueError(
            f"行已收完或已关闭，无法再收货 (line_id={target.id}, status={target.status})"
        )

    remaining = target.qty_ordered - target.qty_received
    if qty > remaining:
        raise ValueError(
            f"行收货数量超出剩余数量：ordered={target.qty_ordered}, "
            f"received={target.qty_received}, try_receive={qty}"
        )

    ref = f"PO-{po.id}"
    reason_val = MovementType.INBOUND.value

    # ✅ ref_line 必须在 (reason, ref) 维度全局递增
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(ref_line), 0)
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = :reason
            """
        ),
        {
            "ref": ref,
            "reason": reason_val,
        },
    )
    max_ref_line = int(row.scalar() or 0)
    next_ref_line = max_ref_line + 1

    await inbound_svc.receive(
        session,
        qty=int(qty),
        ref=ref,
        ref_line=next_ref_line,
        warehouse_id=po.warehouse_id,
        item_id=target.item_id,
        occurred_at=occurred_at or datetime.now(UTC),
        production_date=production_date,
        expiry_date=expiry_date,
    )

    target.qty_received += int(qty)
    now = datetime.now(UTC)

    if target.qty_received == 0:
        target.status = "CREATED"
    elif target.qty_received < target.qty_ordered:
        target.status = "PARTIAL"
    elif target.qty_received == target.qty_ordered:
        target.status = "RECEIVED"
    else:
        target.status = "CLOSED"

    all_zero = all(line.qty_received == 0 for line in po.lines)
    all_full = all(line.qty_received >= line.qty_ordered for line in po.lines)

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

    await session.flush()
    return po
