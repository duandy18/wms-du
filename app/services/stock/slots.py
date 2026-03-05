# app/services/stock/slots.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .dims import norm_batch_code


def _phase4e_legacy_disabled(name: str) -> None:
    raise RuntimeError(
        f"Phase 4E: legacy stocks slot helper '{name}' 已禁用。"
        "stocks 表已退场（rename/drop）；主余额源为 stocks_lot。"
        "请改用 lot-world（stocks_lot + lots）或走 StockService 的 lot 口径。"
    )


async def ensure_stock_slot(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str | None,
) -> None:
    """
    旧时代：在 stocks 维度创建空槽位（qty=0）。

    Phase 4E：禁用。任何调用都应当显式迁移到 lot-world。
    """
    _ = session
    _ = item_id
    _ = warehouse_id
    _ = norm_batch_code(batch_code)
    _phase4e_legacy_disabled("ensure_stock_slot")


async def ensure_stock_row(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str | None = None,
) -> tuple[int, float]:
    """
    旧时代：返回 (stock_id, before_qty)。

    Phase 4E：禁用。任何调用都应当显式迁移到 lot-world。
    """
    _ = session
    _ = item_id
    _ = warehouse_id
    _ = norm_batch_code(batch_code)
    _phase4e_legacy_disabled("ensure_stock_row")
    return (0, 0.0)
