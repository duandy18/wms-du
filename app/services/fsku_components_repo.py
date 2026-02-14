# app/services/fsku_components_repo.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_component_item_ids(session: AsyncSession, *, fsku_id: int) -> list[int]:
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT item_id
                  FROM fsku_components
                 WHERE fsku_id = :fid
                """
            ),
            {"fid": int(fsku_id)},
        )
    ).mappings().all()
    ids = [int(r["item_id"]) for r in rows if r.get("item_id") is not None]
    return sorted(set(ids))
