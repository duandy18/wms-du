# app/services/inventory_ops.py
"""
====================================================================================
📦  INVENTORY OPS SERVICE — 现役搬运服务（A → B 搬移）
====================================================================================

定位说明：

1. InventoryOpsService 是 WMS-DU v2 中仍然在使用的“仓内搬运服务”：
      - 从 A 库位 → B 库位
      - 在同一个 warehouse 内进行
      - 实际库存增减由 StockService.adjust 执行（这非常关键）

2. 它是“现役 A 类服务”，被两个路由使用：
      - app/api/routers/stock_transfer.py
      - app/api/routers/inventory.py

3. 未来重构方向（Phase：Remove Location）：
      - 你现在的 v2 WMS（scan v2、reserve v2、outbound v2）越来越趋向：
            * warehouse_id 作为第一原则
            * 不强依赖 location_id
      - InventoryOpsService 将在未来迁移到：
            * MoveService（按 warehouse/batch/item 粒度）
            * 或纳入 StockService.adjust 的高级操作

4. 在“仓库仍使用 location_id”的过渡阶段，
   本服务继续保持现役地位，但请不要扩展其功能。

唯一真相：
- 所有库存变更仍严格通过 StockService.adjust 完成。
====================================================================================
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService


class InventoryOpsService:
    """
    仓内搬运服务（MOVE）：从 location A 搬到 location B。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.stock = StockService()

    async def move(
        self,
        *,
        item_id: int,
        warehouse_id: int,
        from_location_id: int,
        to_location_id: int,
        qty: int,
        ref: str,
    ) -> dict:
        """
        从 A 库位搬到 B 库位。
        """
        if qty <= 0:
            raise ValueError("qty must be > 0")

        await self.stock.adjust(
            session=self.session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            location_id=from_location_id,
            delta=-qty,
            reason=MovementType.PUTAWAY,
            ref=ref,
        )

        await self.stock.adjust(
            session=self.session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            location_id=to_location_id,
            delta=qty,
            reason=MovementType.PUTAWAY,
            ref=ref,
        )

        return {
            "ok": True,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "from_location_id": from_location_id,
            "to_location_id": to_location_id,
            "qty": qty,
            "ref": ref,
        }
