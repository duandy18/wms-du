# app/services/internal_outbound_query.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.internal_outbound import InternalOutboundDoc


async def get_with_lines(
    session: AsyncSession,
    doc_id: int,
    *,
    for_update: bool = False,
) -> InternalOutboundDoc:
    stmt = (
        select(InternalOutboundDoc)
        .options(selectinload(InternalOutboundDoc.lines))
        .where(InternalOutboundDoc.id == doc_id)
    )
    if for_update:
        stmt = stmt.with_for_update()

    res = await session.execute(stmt)
    doc = res.scalars().first()
    if doc is None:
        raise ValueError(f"InternalOutboundDoc not found: id={doc_id}")

    if doc.lines:
        doc.lines.sort(key=lambda ln: (ln.line_no, ln.id))
    return doc
