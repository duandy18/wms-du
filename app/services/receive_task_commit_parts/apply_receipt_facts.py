# app/services/receive_task_commit_parts/apply_receipt_facts.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_receipt import InboundReceipt
from app.models.purchase_order_line import PurchaseOrderLine
from app.models.receive_task import ReceiveTask, ReceiveTaskLine
from app.services.receive_task_commit_parts.receipt_facts import (
    build_receipt_line,
    ensure_receipt_header,
)


async def ensure_receipt_and_add_line(
    session: AsyncSession,
    *,
    task: ReceiveTask,
    receipt: Optional[InboundReceipt],
    ref: str,
    trace_id: Optional[str],
    now: datetime,
    ref_line: int,
    qty_base: int,
    upc: int,
    task_line: ReceiveTaskLine,
    po_line: Optional[PurchaseOrderLine],
) -> Tuple[Optional[InboundReceipt], bool]:
    """
    凭证事实层（InboundReceipt / InboundReceiptLine）：

    - 第一次遇到实际收货行：创建 receipt header（status=CONFIRMED）
    - 每个实际收货行：插入 receipt line（batch_code NOT NULL，用 NOEXP 做展示占位）

    返回：
    - receipt（可能为 None：例如本次所有 scanned_qty=0）
    - whether_header_created（用于外层调试/统计，可不用）
    """
    receipt, created = ensure_receipt_header(
        task=task,
        receipt=receipt,
        ref=str(ref),
        trace_id=trace_id,
        now=now,
    )
    if created and receipt is not None:
        session.add(receipt)
        await session.flush()

    if receipt is not None:
        receipt_line = build_receipt_line(
            receipt_id=int(receipt.id),  # type: ignore[arg-type]
            ref_line=int(ref_line),
            qty_base=int(qty_base),
            upc=int(upc),
            task_line=task_line,
            po_line=po_line,
        )
        session.add(receipt_line)

    return receipt, created
