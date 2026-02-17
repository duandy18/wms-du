# app/services/inbound_receipt_query.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_receipt import InboundReceipt


async def list_receipts(
    session: AsyncSession,
    *,
    ref: Optional[str] = None,
    trace_id: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    time_from: Optional[datetime] = None,
    time_to: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[InboundReceipt]:
    stmt = (
        select(InboundReceipt)
        .options(selectinload(InboundReceipt.lines))
        .order_by(InboundReceipt.occurred_at.desc(), InboundReceipt.id.desc())
        .offset(max(int(offset), 0))
        .limit(min(max(int(limit), 1), 200))
    )

    if ref:
        stmt = stmt.where(InboundReceipt.ref == ref.strip())
    if trace_id:
        stmt = stmt.where(InboundReceipt.trace_id == trace_id.strip())
    if warehouse_id is not None:
        stmt = stmt.where(InboundReceipt.warehouse_id == int(warehouse_id))
    if source_type:
        stmt = stmt.where(InboundReceipt.source_type == source_type.strip().upper())
    if source_id is not None:
        stmt = stmt.where(InboundReceipt.source_id == int(source_id))
    if time_from is not None:
        stmt = stmt.where(InboundReceipt.occurred_at >= time_from)
    if time_to is not None:
        stmt = stmt.where(InboundReceipt.occurred_at <= time_to)

    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_receipt(
    session: AsyncSession,
    *,
    receipt_id: int,
) -> InboundReceipt:
    stmt = (
        select(InboundReceipt)
        .options(selectinload(InboundReceipt.lines))
        .where(InboundReceipt.id == int(receipt_id))
        .limit(1)
    )
    res = await session.execute(stmt)
    obj = res.scalars().first()
    if obj is None:
        raise ValueError("InboundReceipt not found")
    return obj
