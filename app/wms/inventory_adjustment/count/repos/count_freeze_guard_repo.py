from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_frozen_count_doc_brief(
    session: AsyncSession,
    *,
    warehouse_id: int,
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  count_no,
                  warehouse_id,
                  snapshot_at,
                  status
                FROM count_docs
                WHERE warehouse_id = :warehouse_id
                  AND status = 'FROZEN'
                ORDER BY snapshot_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"warehouse_id": int(warehouse_id)},
        )
    ).mappings().first()

    if row is None:
        return None

    return {
        "id": int(row["id"]),
        "count_no": str(row["count_no"]),
        "warehouse_id": int(row["warehouse_id"]),
        "snapshot_at": row["snapshot_at"],
        "status": str(row["status"]),
    }


__all__ = [
    "get_frozen_count_doc_brief",
]
