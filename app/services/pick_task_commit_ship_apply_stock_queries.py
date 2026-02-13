# app/services/pick_task_commit_ship_apply_stock_queries.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession


_VALID_SCOPES = {"PROD", "DRILL"}


def _norm_scope(scope: Optional[str]) -> str:
    sc = (scope or "").strip().upper() or "PROD"
    if sc not in _VALID_SCOPES:
        raise ValueError("scope must be PROD|DRILL")
    return sc


async def load_on_hand_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str],
    scope: str = "PROD",
) -> int:
    """
    读取当前库存槽位 qty（支持 NULL batch_code）。
    槽位不存在时视为 0。

    ✅ Scope 第一阶段：
    - 默认读取 PROD 口径，避免训练口径混入运营校验
    """
    sc = _norm_scope(scope)

    row = (
        await session.execute(
            SA(
                """
                SELECT qty
                  FROM stocks
                 WHERE scope       = :scope
                   AND warehouse_id = :w
                   AND item_id      = :i
                   AND batch_code IS NOT DISTINCT FROM :c
                 LIMIT 1
                """
            ),
            {"scope": sc, "w": int(warehouse_id), "i": int(item_id), "c": batch_code},
        )
    ).first()

    if not row:
        return 0

    try:
        return int(row[0] or 0)
    except Exception:
        return 0
