# app/services/stock_adjust/db_items.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def item_requires_batch(session: AsyncSession, *, item_id: int) -> bool:
    """
    Phase M 第一阶段：执行层禁止读取 items.has_shelf_life。

    批次受控唯一真相源：items.expiry_policy
    - expiry_policy='REQUIRED' => requires_batch=True
    - 其他（'NONE'/NULL）       => requires_batch=False
    """
    row = (
        await session.execute(
            text(
                """
                SELECT expiry_policy
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
        return str(row[0] or "").upper() == "REQUIRED"
    except Exception:
        return False
