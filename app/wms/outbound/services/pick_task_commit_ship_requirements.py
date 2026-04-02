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
    - expiry_policy='NONE'     => requires_batch=False

    重要：item 不存在时必须明确失败（unknown item 不能默认成 NONE）。
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
        raise ValueError("item_not_found")

    return str(row[0] or "").upper() == "REQUIRED"


def normalize_batch_code(batch_code: Optional[str]) -> Optional[str]:
    if batch_code is None:
        return None
    s = str(batch_code).strip()
    return s or None
