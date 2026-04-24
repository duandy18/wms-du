from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.oms.platforms.models.taobao_order import TaobaoOrder


async def list_taobao_orders(
    session: AsyncSession,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[TaobaoOrder]:
    stmt = (
        sa.select(TaobaoOrder)
        .order_by(
            TaobaoOrder.last_synced_at.desc(),
            TaobaoOrder.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_taobao_order_with_items(
    session: AsyncSession,
    *,
    taobao_order_id: int,
) -> TaobaoOrder | None:
    stmt = (
        sa.select(TaobaoOrder)
        .options(selectinload(TaobaoOrder.items))
        .where(TaobaoOrder.id == taobao_order_id)
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
