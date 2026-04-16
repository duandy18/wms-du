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
    row = await session.execute(
        text(
            """
            SELECT 1
              FROM inbound_receipts
             WHERE source_type = 'PO'
               AND source_id = :po_id
               AND status = :receipt_status
             LIMIT 1
            """
        ),
        {
            "po_id": int(po_id),
            "receipt_status": str(receipt_status).strip().upper(),
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
