# app/wms/stock/services/stock_adjust/lot_code_repo.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_lot_code_for_lot_id(
    session: AsyncSession,
    *,
    lot_id: Optional[int],
) -> Optional[str]:
    if lot_id is None:
        return None
    row = (
        await session.execute(
            text("SELECT lot_code FROM lots WHERE id=:id LIMIT 1"),
            {"id": int(lot_id)},
        )
    ).first()
    if not row:
        return None
    v = row[0]
    if v is None:
        return None
    s = str(v).strip()
    return s or None
