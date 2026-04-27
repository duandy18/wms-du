# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.platform_order_ingestion.models.jd_order import JdOrder


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
