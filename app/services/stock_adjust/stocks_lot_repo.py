# app/services/stock_adjust/stocks_lot_repo.py
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# NOTE:
# - 本模块属于 stock_adjust 执行器内部仓储层（repo）。
# - 业务服务（Inbound/Outbound/Pick/Scan/Dev tools 等）不得直接调用这些函数，
#   必须统一走 StockService.adjust -> adjust_lot_impl，避免绕过合同/幂等/台账。
# - 这里的 SQL 只做“slot 原语 + balance 写入”，不负责 batch/lot 合同裁决。


async def ensure_stocks_lot_slot_exists(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: int,
) -> None:
    # ensure slot (qty=0) for (wh,item,lot)
    await session.execute(
        text(
            """
            INSERT INTO stocks_lot (item_id, warehouse_id, lot_id, qty)
            VALUES (:i, :w, :lot, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot DO NOTHING
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "lot": int(lot_id)},
    )


async def lock_stocks_lot_slot_for_update(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: int,
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
                       AND lot_id = :lot
                     FOR UPDATE
                    """
                ),
                {"i": int(item_id), "w": int(warehouse_id), "lot": int(lot_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(
            f"stocks_lot slot missing for item={item_id}, wh={warehouse_id}, lot_id={lot_id}"
        )
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
