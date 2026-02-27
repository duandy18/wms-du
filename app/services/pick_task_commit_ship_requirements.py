# app/services/pick_task_commit_ship_requirements.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession


async def item_requires_batch(session: AsyncSession, *, item_id: int) -> bool:
    """
    Phase M 第一阶段：执行层禁止读取 items.has_shelf_life。

    批次受控唯一真相源：items.expiry_policy
    - expiry_policy='REQUIRED' => requires_batch=True
    - 其他（'NONE'/NULL）       => requires_batch=False

    重要：item 不存在时返回 False，不在此提前 raise（保持历史测试/调用约定）。
    """
    row = (
        await session.execute(
            SA(
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


def normalize_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None
