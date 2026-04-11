# app/wms/stock/services/lot_guard.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.models.lot import Lot


async def assert_lot_belongs_to(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: Optional[int],
) -> None:
    """
    Phase 4A-2a (Step A):
    强化 lot 写入合法性：当 lot_id 非空时，必须证明 lot 属于对应 (warehouse_id, item_id)。

    约定：
    - lot_id is None => no-op（保持旧行为）
    - lot 不存在 => raise ValueError("lot_not_found")
    - lot 存在但 wh/item 不匹配 => raise ValueError("lot_mismatch")
    """
    if lot_id is None:
        return

    lid = int(lot_id)
    stmt = select(Lot.id, Lot.warehouse_id, Lot.item_id).where(Lot.id == lid).limit(1)
    row = (await session.execute(stmt)).first()
    if row is None:
        raise ValueError("lot_not_found")

    _, lot_wh, lot_item = row
    if int(lot_wh) != int(warehouse_id) or int(lot_item) != int(item_id):
        raise ValueError("lot_mismatch")
