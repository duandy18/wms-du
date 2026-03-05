# app/services/stock/mutate.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


def _phase4e_legacy_disabled(name: str) -> None:
    raise RuntimeError(
        f"Phase 4E: legacy stock mutate '{name}' 已禁用。"
        "禁止使用 legacy stocks 表的任何维度/ID 进行加减或查询；"
        "请改用 lot-world（stocks_lot + lots）并通过 StockService/lot 口径实现。"
    )


async def bump_stock_by_stock_id(session: AsyncSession, *, stock_id: int, delta: float) -> None:
    """旧时代：按 legacy stocks.id 精确加减。Phase 4E 禁用。"""
    _ = session
    _ = stock_id
    _ = delta
    _phase4e_legacy_disabled("bump_stock_by_stock_id")


async def bump_stock(session: AsyncSession, *, item_id: int, warehouse_id: int, delta: float) -> None:
    """旧时代：按 item+warehouse 粗粒度更新 legacy stocks。Phase 4E 禁用。"""
    _ = session
    _ = item_id
    _ = warehouse_id
    _ = delta
    _phase4e_legacy_disabled("bump_stock")


async def get_current_qty(session: AsyncSession, *, item_id: int, warehouse_id: int) -> float:
    """旧时代：汇总 legacy stocks qty。Phase 4E 禁用。"""
    _ = session
    _ = item_id
    _ = warehouse_id
    _phase4e_legacy_disabled("get_current_qty")
    return 0.0
