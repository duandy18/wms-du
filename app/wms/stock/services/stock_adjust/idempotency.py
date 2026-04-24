# app/wms/stock/services/stock_adjust/idempotency.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def idem_hit_by_lot_key(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
    reason: str,
    ref: str,
    ref_line: int,
) -> bool:
    """
    Phase M-2 终态（lot-only）：

    - stock_ledger 不再存在 lot_id_key / batch_code_key
    - 幂等锚点与 DB 唯一约束保持 1:1：
      (warehouse_id, item_id, lot_id, reason, ref, ref_line)
    """
    idem = await session.execute(
        text(
            """
            SELECT 1
              FROM stock_ledger
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_id       = :lot
               AND reason       = :r
               AND ref          = :ref
               AND ref_line     = :rl
             LIMIT 1
            """
        ),
        {
            "w": int(warehouse_id),
            "i": int(item_id),
            "lot": int(lot_id),
            "r": str(reason),
            "ref": str(ref),
            "rl": int(ref_line),
        },
    )
    return idem.scalar_one_or_none() is not None
