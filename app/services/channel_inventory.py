from __future__ import annotations

# Legacy shim:
# - keep import path stable
# - no SQL / no business logic here

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_inventory_service import ChannelInventoryService as _ImplService
from app.services.channel_inventory_types import BatchQty, ChannelInventory


class ChannelInventoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._impl = _ImplService(session=session)

    async def get_single_item(
        self, platform: str, shop_id: str, warehouse_id: int, item_id: int
    ) -> ChannelInventory:
        return await self._impl.get_single_item(
            platform=platform, shop_id=shop_id, warehouse_id=warehouse_id, item_id=item_id
        )

    async def get_multi_item(
        self, platform: str, shop_id: str, item_id: int
    ) -> List[ChannelInventory]:
        return await self._impl.get_multi_item(platform=platform, shop_id=shop_id, item_id=item_id)

    async def get_multi_item_for_store(
        self, platform: str, shop_id: str, item_id: int
    ) -> List[ChannelInventory]:
        return await self._impl.get_multi_item_for_store(
            platform=platform, shop_id=shop_id, item_id=item_id
        )


__all__ = ["BatchQty", "ChannelInventory", "ChannelInventoryService"]
