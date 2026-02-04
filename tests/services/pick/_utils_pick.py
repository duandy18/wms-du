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
    row = await session.execute(text("SELECT COUNT(*) FROM stocks"))
    return int(row.scalar_one())


async def force_no_stock(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: Optional[str] = None,
) -> None:
    if batch_code is None:
        await session.execute(
            text("DELETE FROM stocks WHERE warehouse_id = :w AND item_id = :i"),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
        return

    await session.execute(
        text(
            """
            DELETE FROM stocks
             WHERE warehouse_id = :w
               AND item_id = :i
               AND batch_code IS NOT DISTINCT FROM :b
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "b": batch_code},
    )
