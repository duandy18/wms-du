# app/wms/stock/services/stock_adjust/legacy_stocks_repo.py
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


async def ensure_stock_slot_exists(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code_norm: Optional[str],
) -> None:
    _ = session
    _ = item_id
    _ = warehouse_id
    _ = batch_code_norm
    raise RuntimeError(
        "Phase 4E: legacy stocks repo 禁用（禁止读取/写入 legacy stocks）。请改用 lot-world（stocks_lot + lots）。"
    )


async def lock_stock_slot_for_update(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code_norm: Optional[str],
) -> tuple[int, int]:
    _ = session
    _ = item_id
    _ = warehouse_id
    _ = batch_code_norm
    raise RuntimeError(
        "Phase 4E: legacy stocks repo 禁用（禁止读取/写入 legacy stocks）。请改用 lot-world（stocks_lot + lots）。"
    )


async def apply_stock_delta(
    session: AsyncSession,
    *,
    stock_id: int,
    delta: int,
) -> None:
    _ = session
    _ = stock_id
    _ = delta
    raise RuntimeError(
        "Phase 4E: legacy stocks repo 禁用（禁止读取/写入 legacy stocks）。请改用 lot-world（stocks_lot + lots）。"
    )
