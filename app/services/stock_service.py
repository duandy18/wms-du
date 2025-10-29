# app/services/stock_service.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inventory_adjust import InventoryAdjust
from app.services.reconcile_service import ReconcileService
from app.services.stock_helpers import ensure_item


class StockService:
    """门面服务：只负责路由，不直接操作库存。"""

    async def adjust(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        location_id: int,
        delta: float,
        reason: str,
        ref: str | None = None,
        batch_code: str | None = None,
        production_date=None,
        expiry_date=None,
        mode: str = "NORMAL",
        allow_expired: bool = False,
    ) -> dict:
        """
        统一入口：
        - delta > 0 → 入库 (InventoryAdjust.inbound)
        - delta < 0 → 出库 (InventoryAdjust.fefo_outbound)
        - delta = 0 → 不变
        注意：
            * 本层不再调用任何 bump_stock/bump_stock_by_stock_id。
            * 实际的库存变更与 Ledger 写入完全由 InventoryAdjust 执行。
        """
        # 确保商品存在
        await ensure_item(session, item_id=item_id)
        mode = (mode or "NORMAL").upper()

        # 零变更直接返回
        if delta == 0:
            return {"ok": True, "delta": 0.0}

        # 出库（负数）
        if delta < 0:
            return await InventoryAdjust.fefo_outbound(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=float(delta),  # fefo_outbound 约定负值扣减
                reason=reason,
                ref=ref,
                allow_expired=allow_expired,
                batch_code=batch_code,
            )

        # 入库（正数）
        if not batch_code:
            # 若未提供批次，生成确定性默认批次码
            batch_code = f"AUTO-{item_id}-{location_id}"

        return await InventoryAdjust.inbound(
            session=session,
            item_id=item_id,
            location_id=location_id,
            delta=float(delta),
            reason=reason,
            ref=ref,
            batch_code=batch_code,
            production_date=production_date,
            expiry_date=expiry_date,
        )

    async def reconcile_inventory(
        self,
        *,
        session: AsyncSession,
        item_id: int,
        location_id: int,
        counted_qty: float,
        apply: bool = True,
        ref: str | None = None,
    ) -> dict:
        """
        库存盘点对账。
        """
        return await ReconcileService.reconcile_inventory(
            session=session,
            item_id=item_id,
            location_id=location_id,
            counted_qty=counted_qty,
            apply=apply,
            ref=ref,
        )
