from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.jd_order import JdOrder


async def list_jd_orders(
    session: AsyncSession,
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[JdOrder]:
    stmt = (
        sa.select(JdOrder)
        .order_by(JdOrder.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_jd_order_with_items(
    session: AsyncSession,
    *,
    jd_order_id: int,
) -> JdOrder | None:
    stmt = (
        sa.select(JdOrder)
        .where(JdOrder.id == jd_order_id)
        .options(selectinload(JdOrder.items))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
