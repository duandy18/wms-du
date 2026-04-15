# app/procurement/repos/receipt_draft_repo.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.models.inbound_receipt import InboundReceipt
from app.procurement.models.purchase_order import PurchaseOrder


async def get_latest_po_draft_receipt(
    session: AsyncSession, *, po_id: int
) -> Optional[InboundReceipt]:
    stmt = (
        select(InboundReceipt)
        .where(InboundReceipt.source_type == "PO")
        .where(InboundReceipt.source_id == int(po_id))
        .where(InboundReceipt.status == "DRAFT")
        .order_by(InboundReceipt.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalars().first()


async def create_po_draft_receipt(
    session: AsyncSession,
    *,
    po: PurchaseOrder,
    occurred_at: datetime,
) -> InboundReceipt:
    ts = int(occurred_at.timestamp() * 1000)
    ref = f"DRFT-PO-{po.id}-{ts}"

    r = InboundReceipt(
        warehouse_id=int(po.warehouse_id),
        supplier_id=getattr(po, "supplier_id", None),
        supplier_name=getattr(po, "supplier_name", None),
        source_type="PO",
        source_id=int(po.id),
        ref=ref,
        trace_id=None,
        status="DRAFT",
        remark="explicit draft (Phase5)",
        occurred_at=occurred_at,
    )
    session.add(r)
    await session.flush()
    return r


async def get_or_create_po_draft_receipt_explicit(
    session: AsyncSession,
    *,
    po: PurchaseOrder,
    occurred_at: datetime,
) -> InboundReceipt:
    draft = await get_latest_po_draft_receipt(session, po_id=int(po.id))
    if draft is not None:
        return draft

    try:
        return await create_po_draft_receipt(session, po=po, occurred_at=occurred_at)
    except IntegrityError:
        await session.rollback()
        draft2 = await get_latest_po_draft_receipt(session, po_id=int(po.id))
        if draft2 is not None:
            return draft2
        raise


async def next_receipt_line_no(session: AsyncSession, *, receipt_id: int) -> int:
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(line_no), 0) AS mx
              FROM inbound_receipt_lines
             WHERE receipt_id = :rid
            """
        ),
        {"rid": int(receipt_id)},
    )
    mx = int(row.scalar() or 0)
    return mx + 1


async def sum_confirmed_received_base(
    session: AsyncSession, *, po_id: int, po_line_id: int
) -> int:
    sql = text(
        """
        SELECT COALESCE(SUM(rl.qty_base), 0)::int AS qty
          FROM inbound_receipt_lines rl
          JOIN inbound_receipts r
            ON r.id = rl.receipt_id
         WHERE r.source_type='PO'
           AND r.source_id=:po_id
           AND r.status='CONFIRMED'
           AND rl.po_line_id=:po_line_id
        """
    )
    return int(
        (await session.execute(sql, {"po_id": int(po_id), "po_line_id": int(po_line_id)})).scalar()
        or 0
    )


async def sum_draft_received_base(
    session: AsyncSession, *, receipt_id: int, po_line_id: int
) -> int:
    sql = text(
        """
        SELECT COALESCE(SUM(qty_base), 0)::int AS qty
          FROM inbound_receipt_lines
         WHERE receipt_id=:rid
           AND po_line_id=:po_line_id
        """
    )
    return int(
        (await session.execute(sql, {"rid": int(receipt_id), "po_line_id": int(po_line_id)})).scalar()
        or 0
    )


__all__ = [
    "get_latest_po_draft_receipt",
    "create_po_draft_receipt",
    "get_or_create_po_draft_receipt_explicit",
    "next_receipt_line_no",
    "sum_confirmed_received_base",
    "sum_draft_received_base",
]
