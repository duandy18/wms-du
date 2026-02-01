# app/services/pick_task_commit_ship_requirements.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession


async def item_requires_batch(session: AsyncSession, *, item_id: int) -> bool:
    row = (
        await session.execute(
            SA(
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


def normalize_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None
