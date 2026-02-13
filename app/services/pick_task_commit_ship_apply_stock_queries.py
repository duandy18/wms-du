# app/services/pick_task_commit_ship_apply_stock_queries.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession


async def load_on_hand_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str],
) -> int:
    """
    读取当前库存槽位 qty（支持 NULL batch_code）。
    槽位不存在时视为 0。
    """
    row = (
        await session.execute(
            SA(
                """
                SELECT qty
                  FROM stocks
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND batch_code IS NOT DISTINCT FROM :c
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": batch_code},
        )
    ).first()

    if not row:
        return 0

    try:
        return int(row[0] or 0)
    except Exception:
        return 0
