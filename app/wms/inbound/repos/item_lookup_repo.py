from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.pms.public.items.contracts.item_policy import ItemPolicy
from app.pms.public.items.services.item_read_service import ItemReadService


async def get_item_policy_by_id(
    session: AsyncSession,
    *,
    item_id: int,
) -> ItemPolicy | None:
    svc = ItemReadService(session)
    return await svc.aget_policy_by_id(item_id=int(item_id))


__all__ = ["get_item_policy_by_id"]
