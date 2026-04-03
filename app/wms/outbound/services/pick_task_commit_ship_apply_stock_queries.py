# app/wms/outbound/services/pick_task_commit_ship_apply_stock_queries.py
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
    Phase 4D：
    - 只读：stocks_lot（lot-world）
    - 禁止：fallback 读取 legacy stocks

    batch_code 语义：
    - 在 lot-world 下作为展示码 lot_code（允许 NULL）
    - lot_id 为空时 LEFT JOIN lots 得到 lot_code=NULL，与 batch_code=NULL 精确匹配（IS NOT DISTINCT FROM）

    注意：
    - 这里的目的仅用于错误提示/可行动明细，不参与扣减原子性裁决。
    """
    row = (
        await session.execute(
            SA(
                """
                SELECT COALESCE(SUM(s.qty), 0) AS qty
                FROM stocks_lot s
                LEFT JOIN lots lo ON lo.id = s.lot_id
                WHERE s.warehouse_id = :w
                  AND s.item_id      = :i
                  AND lo.lot_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
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
