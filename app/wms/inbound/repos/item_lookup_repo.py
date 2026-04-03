from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item


async def get_item_by_id(
    session: AsyncSession,
    *,
    item_id: int,
) -> Item | None:
    stmt = select(Item).where(Item.id == int(item_id))
    return (await session.execute(stmt)).scalars().first()


__all__ = ["get_item_by_id"]
