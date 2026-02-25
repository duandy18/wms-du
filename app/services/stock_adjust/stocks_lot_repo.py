# app/services/stock_adjust/stocks_lot_repo.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stock_adjust.batch_keys import lot_key


async def ensure_stocks_lot_slot_exists(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: Optional[int],
) -> None:
    """
    确保 stocks_lot 槽位存在（lot_id 允许 NULL，映射 lot_id_key=0）。
    """
    await session.execute(
        text(
            """
            INSERT INTO stocks_lot (item_id, warehouse_id, lot_id, qty)
            VALUES (:i, :w, :lot, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot DO NOTHING
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "lot": (int(lot_id) if lot_id is not None else None)},
    )


async def lock_stocks_lot_slot_for_update(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: Optional[int],
) -> tuple[int, int]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT id AS sid, qty AS q
                      FROM stocks_lot
                     WHERE item_id=:i
                       AND warehouse_id=:w
                       AND lot_id_key = :lk
                     FOR UPDATE
                    """
                ),
                {"i": int(item_id), "w": int(warehouse_id), "lk": lot_key(lot_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(f"stocks_lot slot missing for item={item_id}, wh={warehouse_id}, lot_id={lot_id}")
    return int(row["sid"]), int(row["q"])


async def apply_stocks_lot_set_qty(
    session: AsyncSession,
    *,
    slot_id: int,
    new_qty: int,
) -> None:
    await session.execute(
        text("UPDATE stocks_lot SET qty = :q WHERE id = :sid"),
        {"q": int(new_qty), "sid": int(slot_id)},
    )
