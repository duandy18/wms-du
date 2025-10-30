from __future__ import annotations

from typing import Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_adjust import InventoryAdjust


class ReconcileService:
    """
    盘点对账：counted - on_hand = diff
      - diff > 0 → 上调（CYCLE_COUNT_UP）
      - diff < 0 → 下调（CYCLE_COUNT_DOWN，走 FEFO）
    """

    @staticmethod
    async def reconcile_inventory(
        *,
        session: AsyncSession,
        item_id: int,
        location_id: int,
        counted_qty: int,
        ref: str | None = None,
    ) -> Dict:
        row = await session.execute(
            text("SELECT qty FROM stocks WHERE item_id=:iid AND location_id=:loc LIMIT 1"),
            {"iid": item_id, "loc": location_id},
        )
        on_hand = int(row.scalar() or 0)
        diff = int(counted_qty) - on_hand
        if diff == 0:
            return {"ok": True, "delta": 0, "after": on_hand}

        if diff > 0:
            res = await InventoryAdjust.inbound(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=diff,
                reason="CYCLE_COUNT_UP",
                ref=ref or f"CC-UP-{item_id}-{location_id}",
                batch_code=f"CC-{item_id}-{location_id}",
                production_date=None,
                expiry_date=None,
            )
            return {"ok": True, "delta": diff, **res}
        else:
            res = await InventoryAdjust.fefo_outbound(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=diff,  # 负数
                reason="CYCLE_COUNT_DOWN",
                ref=ref or f"CC-DN-{item_id}-{location_id}",
                allow_expired=True,
            )
            return {"ok": True, "delta": diff, **res}
