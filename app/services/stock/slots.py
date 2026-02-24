# app/services/stock/slots.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .dims import norm_batch_code


async def ensure_stock_slot(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str | None,
) -> None:
    """
    在 stocks 维度的“空槽位”（qty=0）。

    ✅ DB 唯一性：uq_stocks_item_wh_batch = (item_id, warehouse_id, batch_code_key)
    - batch_code 允许 None（无批次槽位）
    """
    bc_norm = norm_batch_code(batch_code)
    await session.execute(
        text(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:i, :w, :c, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO NOTHING
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "c": bc_norm},
    )


async def ensure_stock_row(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str | None = None,
) -> tuple[int, float]:
    """
    返回：stock_id, before_qty（按当前唯一维度：item_id + warehouse_id + batch_code_key）
    """
    bc_norm = norm_batch_code(batch_code)

    await ensure_stock_slot(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        batch_code=bc_norm,
    )

    row = await session.execute(
        text(
            """
            SELECT id, qty
              FROM stocks
             WHERE item_id=:i
               AND warehouse_id=:w
               AND batch_code IS NOT DISTINCT FROM :c
             LIMIT 1
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "c": bc_norm},
    )
    rec = row.first()
    if not rec:
        raise RuntimeError("ensure_stock_row failed to materialize stock row")
    return int(rec[0]), float(rec[1] or 0.0)
