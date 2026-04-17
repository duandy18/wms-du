# app/procurement/repos/purchase_order_update_repo.py
from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.models.purchase_order_line import PurchaseOrderLine


async def _has_po_receipt_in_status(
    session: AsyncSession,
    *,
    po_id: int,
    receipt_status: str,
) -> bool:
    """
    旧语义兼容映射：

    - 旧链里的“CONFIRMED 收货单”在新链下不再存在；
    - 对采购编辑/更新阻断来说，最接近的等价条件是：
      已存在 source_type='PURCHASE_ORDER' 且 source_doc_id=po_id 的 RELEASED 入库任务单。
    - DRAFT 不阻断；VOIDED 不阻断。
    """
    normalized = str(receipt_status).strip().upper()

    # 旧调用方仍然传 CONFIRMED，这里把它映射到新任务层 RELEASED。
    if normalized == "CONFIRMED":
        normalized = "RELEASED"

    row = await session.execute(
        text(
            """
            SELECT 1
              FROM inbound_receipts
             WHERE source_type = 'PURCHASE_ORDER'
               AND source_doc_id = :po_id
               AND status = :receipt_status
             LIMIT 1
            """
        ),
        {
            "po_id": int(po_id),
            "receipt_status": normalized,
        },
    )
    return row.first() is not None


async def has_po_confirmed_receipt(
    session: AsyncSession,
    *,
    po_id: int,
) -> bool:
    return await _has_po_receipt_in_status(session, po_id=po_id, receipt_status="CONFIRMED")


async def has_po_committed_inbound_facts(
    session: AsyncSession,
    *,
    po_id: int,
) -> bool:
    row = await session.execute(
        text(
            """
            SELECT 1
              FROM purchase_order_lines pol
              JOIN inbound_event_lines iel
                ON iel.po_line_id = pol.id
              JOIN wms_events we
                ON we.id = iel.event_id
             WHERE pol.po_id = :po_id
               AND we.event_type = 'INBOUND'
               AND we.source_type = 'PURCHASE_ORDER'
               AND we.event_kind = 'COMMIT'
               AND we.status = 'COMMITTED'
             LIMIT 1
            """
        ),
        {"po_id": int(po_id)},
    )
    return row.first() is not None


async def replace_purchase_order_lines(
    session: AsyncSession,
    *,
    po_id: int,
    lines: Sequence[dict[str, Any]],
) -> None:
    await session.execute(
        text("DELETE FROM purchase_order_lines WHERE po_id = :po_id"),
        {"po_id": int(po_id)},
    )
    await session.flush()

    for line in lines:
        session.add(PurchaseOrderLine(po_id=int(po_id), **dict(line)))
    await session.flush()


__all__ = [
    "has_po_confirmed_receipt",
    "has_po_committed_inbound_facts",
    "replace_purchase_order_lines",
]
