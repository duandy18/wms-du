# tests/services/pick/_utils_pick.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def build_handoff_code(order_ref: str) -> str:
    return f"HC:{str(order_ref)}"


def get_task_ref(task: dict) -> str:
    if isinstance(task, dict):
        ref = task.get("ref")
        if isinstance(ref, str) and ref:
            return ref
        ref2 = task.get("order_ref")
        if isinstance(ref2, str) and ref2:
            return ref2
        tid = task.get("id")
        if tid is not None:
            return f"PICKTASK:{int(tid)}"
    return "PICKTASK:UNKNOWN"


async def ledger_count(session: AsyncSession) -> int:
    row = await session.execute(text("SELECT COUNT(*) FROM stock_ledger"))
    return int(row.scalar_one())


async def stocks_count(session: AsyncSession) -> int:
    """
    Phase 4D：
    - 测试口径以 stocks_lot 为准（lot-world）
    - Phase 4E：以 stocks_lot 为唯一余额源；legacy 表不再作为判断依据
    """
    row = await session.execute(text("SELECT COUNT(*) FROM stocks_lot"))
    return int(row.scalar_one())


async def force_no_stock(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str] = None,
) -> None:
    """
    Phase 4D：
    - 强制清空库存应操作 stocks_lot（lot-world 真相）
    - batch_code 语义：lot_code（SUPPLIER）展示码
    """
    if batch_code is None:
        # 清空该 item/warehouse 下所有 lot 槽位（含 lot_id=NULL 的 lot_id_key=0 槽位）
        await session.execute(
            text("DELETE FROM stocks_lot WHERE warehouse_id = :w AND item_id = :i"),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
        return

    await session.execute(
        text(
            """
            DELETE FROM stocks_lot sl
             WHERE sl.warehouse_id = :w
               AND sl.item_id      = :i
               AND sl.lot_id IN (
                   SELECT id
                     FROM lots
                    WHERE warehouse_id = :w
                      AND item_id      = :i
                      AND lot_code_source = 'SUPPLIER'
                      AND lot_code IS NOT DISTINCT FROM :c
               )
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "c": str(batch_code)},
    )
