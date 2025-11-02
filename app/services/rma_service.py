from __future__ import annotations

from typing import Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_adjust import InventoryAdjust


class RMAService:
    """
    逆向流程：
      - 良品回库：正向入库（RETURN_IN）
      - 次品隔离：从原位扣减（RMA_QUAR_OUT）→ 隔离位增加（RMA_QUAR_IN）
    """

    async def return_good(
        self, *, session: AsyncSession, ref: str, item_id: int, location_id: int, qty: int
    ) -> Dict:
        return await InventoryAdjust.inbound(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=abs(qty),
            reason="RETURN_IN",
            ref=ref,
            batch_code=f"RMA-{item_id}-{location_id}",  # 可替换为来源批次码映射
            production_date=None,
            expiry_date=None,
        )

    async def return_defect(
        self,
        *,
        session: AsyncSession,
        ref: str,
        item_id: int,
        from_location_id: int,
        quarantine_location_id: int,
        qty: int,
    ) -> Dict:
        # 先从原位扣减（FEFO）
        await InventoryAdjust.fefo_outbound(
            session=session,
            item_id=item_id,
            location_id=from_location_id,
            delta=-abs(qty),
            reason="RMA_QUAR_OUT",
            ref=ref,
            allow_expired=True,
        )
        # 再入隔离位
        res = await InventoryAdjust.inbound(
            session=session,
            item_id=item_id,
            location_id=quarantine_location_id,
            delta=abs(qty),
            reason="RMA_QUAR_IN",
            ref=ref,
            batch_code=f"QUAR-{item_id}-{quarantine_location_id}",
            production_date=None,
            expiry_date=None,
        )
        return res
