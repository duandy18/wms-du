# app/services/stock_adjust/idempotency.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_adjust.batch_keys import batch_key, lot_key


async def idem_hit_by_lot_and_batch_key(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code_norm: Optional[str],
    lot_id: Optional[int],
    reason: str,
    ref: str,
    ref_line: int,
) -> bool:
    idem = await session.execute(
        text(
            """
            SELECT 1
              FROM stock_ledger
             WHERE warehouse_id   = :w
               AND item_id        = :i
               AND lot_id_key     = :lk
               AND batch_code_key = :ck
               AND reason         = :r
               AND ref            = :ref
               AND ref_line       = :rl
             LIMIT 1
            """
        ),
        {
            "w": int(warehouse_id),
            "i": int(item_id),
            "lk": lot_key(lot_id),
            "ck": batch_key(batch_code_norm),
            "r": str(reason),
            "ref": str(ref),
            "rl": int(ref_line),
        },
    )
    return idem.scalar_one_or_none() is not None
