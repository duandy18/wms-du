from __future__ import annotations

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_receipt import InboundReceipt
from app.pms.public.items.contracts.item_basic import ItemBasic
from app.pms.public.items.services.item_read_service import ItemReadService


async def load_receipt_for_update(
    session: AsyncSession,
    *,
    receipt_id: int,
) -> InboundReceipt:
    stmt = (
        select(InboundReceipt)
        .options(selectinload(InboundReceipt.lines))
        .where(InboundReceipt.id == int(receipt_id))
        .with_for_update()
    )
    obj = (await session.execute(stmt)).scalars().first()
    if obj is None:
        raise ValueError("InboundReceipt not found")
    if obj.lines:
        obj.lines.sort(
            key=lambda x: (
                int(getattr(x, "line_no", 0) or 0),
                int(getattr(x, "id", 0) or 0),
            )
        )
    return obj


async def load_items_by_ids(
    session: AsyncSession,
    *,
    item_ids: List[int],
) -> Dict[int, ItemBasic]:
    if not item_ids:
        return {}

    svc = ItemReadService(session)
    return await svc.aget_basics_by_item_ids(item_ids=[int(x) for x in item_ids])


__all__ = [
    "load_receipt_for_update",
    "load_items_by_ids",
]
