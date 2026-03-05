# app/services/stock/ensure.py
from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item

from .retry import exec_retry


async def ensure_item(session: AsyncSession, item_id: int) -> None:
    exists = (await session.execute(select(Item.id).where(Item.id == item_id))).scalar_one_or_none()
    if exists is not None:
        return
    try:
        await exec_retry(
            session,
            insert(Item).values({"id": item_id, "sku": f"ITEM-{item_id}", "name": f"Auto Item {item_id}"}),
        )
    except IntegrityError:
        await session.rollback()
