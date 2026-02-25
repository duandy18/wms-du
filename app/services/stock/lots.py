# app/services/stock/lots.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_lot_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_code: str,
    production_date,
    expiry_date,
) -> int:
    """
    Phase 4E（真收口）：
    - 批次主档统一迁移到 lots（SUPPLIER lot）
    - 返回 lot_id（幂等）
    """
    code = str(lot_code).strip()
    if not code:
        raise ValueError("lot_code empty")

    row = await session.execute(
        text(
            """
            INSERT INTO lots(
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                production_date,
                expiry_date,
                expiry_source
            )
            VALUES (:w, :i, 'SUPPLIER', :code, :prod, :exp, :exp_src)
            ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
            WHERE lot_code_source = 'SUPPLIER'
            DO UPDATE SET expiry_date = COALESCE(lots.expiry_date, EXCLUDED.expiry_date)
            RETURNING id
            """
        ),
        {
            "w": int(warehouse_id),
            "i": int(item_id),
            "code": code,
            "prod": production_date,
            "exp": expiry_date,
            "exp_src": ("EXPLICIT" if expiry_date is not None else None),
        },
    )
    got = row.scalar_one_or_none()
    if got is not None:
        return int(got)

    row2 = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'SUPPLIER'
               AND lot_code     = :code
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "code": code},
    )
    got2 = row2.scalar_one_or_none()
    if got2 is None:
        raise RuntimeError("ensure_lot_full failed to materialize lot row")
    return int(got2)


# 兼容旧调用名：仍保留函数入口，但内部语义是 lot-world
async def ensure_batch_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    production_date,
    expiry_date,
) -> int:
    return await ensure_lot_full(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=batch_code,
        production_date=production_date,
        expiry_date=expiry_date,
    )
