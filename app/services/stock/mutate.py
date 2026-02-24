# app/services/stock/mutate.py
from __future__ import annotations

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock

from .accessors import stock_qty_col
from .retry import exec_retry


async def bump_stock_by_stock_id(session: AsyncSession, *, stock_id: int, delta: float) -> None:
    """按 stocks.id 精确加减。"""
    qcol = stock_qty_col()
    await exec_retry(
        session,
        update(Stock).where(Stock.id == stock_id).values({qcol.key: func.coalesce(qcol, 0) + float(delta)}),
    )


async def bump_stock(session: AsyncSession, *, item_id: int, warehouse_id: int, delta: float) -> None:
    """
    无 location 版本：对该 warehouse 下该 item 的所有批次行做汇总更新。

    如果该 item 在该 warehouse 下没有任何 stocks 行，则创建一个 “无批次(NULL) 槽位” 来承接 delta。
    """
    qcol = stock_qty_col()

    any_sid = (
        await session.execute(
            select(Stock.id).where(Stock.item_id == int(item_id), Stock.warehouse_id == int(warehouse_id)).limit(1)
        )
    ).scalar_one_or_none()

    if any_sid is None:
        await exec_retry(
            session,
            insert(Stock).values(
                {
                    "item_id": int(item_id),
                    "warehouse_id": int(warehouse_id),
                    "batch_code": None,
                    qcol.key: float(delta),
                }
            ),
        )
        return

    await exec_retry(
        session,
        update(Stock)
        .where(Stock.item_id == int(item_id), Stock.warehouse_id == int(warehouse_id))
        .values({qcol.key: func.coalesce(qcol, 0) + float(delta)}),
    )


async def get_current_qty(session: AsyncSession, *, item_id: int, warehouse_id: int) -> float:
    """
    无 location 版本：汇总该 warehouse 下该 item 的 qty。
    """
    qcol = stock_qty_col()
    val = (
        await session.execute(
            select(func.coalesce(func.sum(qcol), 0)).where(
                Stock.item_id == int(item_id), Stock.warehouse_id == int(warehouse_id)
            )
        )
    ).scalar_one()
    return float(val or 0.0)
