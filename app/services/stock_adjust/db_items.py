# app/services/stock_adjust/db_items.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def item_requires_batch(session: AsyncSession, *, item_id: int) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT has_shelf_life
                  FROM items
                 WHERE id = :item_id
                 LIMIT 1
                """
            ),
            {"item_id": int(item_id)},
        )
    ).first()
    if not row:
        return False
    try:
        return bool(row[0] is True)
    except Exception:
        return False
