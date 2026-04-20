from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def query_outbound_lot_candidates(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
) -> list[dict[str, Any]]:
    sql = text(
        """
        SELECT
          s.lot_id,
          l.lot_code AS lot_code,
          l.production_date AS production_date,
          l.expiry_date AS expiry_date,
          s.qty AS available_qty
        FROM stocks_lot AS s
        LEFT JOIN lots AS l
          ON l.id = s.lot_id
        WHERE s.warehouse_id = :warehouse_id
          AND s.item_id = :item_id
          AND s.qty > 0
        ORDER BY
          l.expiry_date ASC NULLS LAST,
          l.production_date ASC NULLS LAST,
          l.lot_code ASC NULLS LAST,
          s.lot_id ASC
        """
    )
    rows = (
        await session.execute(
            sql,
            {
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
            },
        )
    ).mappings().all()
    return [dict(r) for r in rows]


__all__ = ["query_outbound_lot_candidates"]
