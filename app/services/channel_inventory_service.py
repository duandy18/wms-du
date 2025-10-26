from __future__ import annotations

from typing import Optional

from sqlalchemy import select, insert, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import ChannelInventory


class ChannelInventoryService:
    """
    只负责维护渠道侧的 reserved_qty，并提供可选的 visible 回写。
    不触碰核心库存与台账（那些仍由 StockService / OutboundService 主导）。
    """

    @staticmethod
    async def _ensure_row(session: AsyncSession, *, store_id: int, item_id: int) -> int:
        rid = (
            await session.execute(
                select(ChannelInventory.id).where(
                    ChannelInventory.store_id == store_id,
                    ChannelInventory.item_id == item_id,
                )
            )
        ).scalar_one_or_none()
        if rid:
            return int(rid)
        rid = (
            await session.execute(
                insert(ChannelInventory)
                .values(store_id=store_id, item_id=item_id, reserved_qty=0, visible_qty=0)
                .returning(ChannelInventory.id)
            )
        ).scalar_one()
        await session.commit()
        return int(rid)

    @staticmethod
    async def adjust_reserved(
        session: AsyncSession,
        *,
        store_id: int,
        item_id: int,
        delta: int,
    ) -> int:
        """
        维护 reserved_qty：delta>0 表示占用，delta<0 表示释放或发货扣减。
        返回最新 reserved_qty。
        """
        await ChannelInventoryService._ensure_row(session, store_id=store_id, item_id=item_id)

        cur = (
            await session.execute(
                select(ChannelInventory.reserved_qty).where(
                    ChannelInventory.store_id == store_id, ChannelInventory.item_id == item_id
                )
            )
        ).scalar_one()
        new_val = int(cur or 0) + int(delta)
        if new_val < 0:
            # 不允许出现负值 —— 幂等与顺序错乱时保护
            new_val = 0

        await session.execute(
            update(ChannelInventory)
            .where(ChannelInventory.store_id == store_id, ChannelInventory.item_id == item_id)
            .values(reserved_qty=new_val)
        )
        await session.commit()
        return new_val

    @staticmethod
    async def set_visible(
        session: AsyncSession,
        *,
        store_id: int,
        item_id: int,
        visible: int,
    ) -> None:
        await ChannelInventoryService._ensure_row(session, store_id=store_id, item_id=item_id)
        await session.execute(
            update(ChannelInventory)
            .where(ChannelInventory.store_id == store_id, ChannelInventory.item_id == item_id)
            .values(visible_qty=int(max(visible, 0)))
        )
        await session.commit()
