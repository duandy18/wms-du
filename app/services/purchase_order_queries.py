# app/services/purchase_order_queries.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.purchase_order import PurchaseOrder


async def get_po_with_lines(
    session: AsyncSession,
    po_id: int,
    *,
    for_update: bool = False,
) -> Optional[PurchaseOrder]:
    """
    获取带行的采购单（头 + 行）。
    """
    stmt = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines))
        .where(PurchaseOrder.id == po_id)
    )
    if for_update:
        stmt = stmt.with_for_update()

    res = await session.execute(stmt)
    po = res.scalars().first()
    if po is None:
        return None

    if po.lines:
        po.lines.sort(key=lambda line: (line.line_no, line.id))
    return po
