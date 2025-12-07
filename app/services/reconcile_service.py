# app/services/reconcile_service.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService


class ReconcileService:
    """
    盘点/对账服务（统一走 StockService，不直连 SQL）：
    - 不控事务；外层决定事务边界；
    - 结构化返回，纯业务字段；
    - 幂等与原子性由 StockService 内部的“ref + 行锁/唯一键”保障。
    """

    def __init__(self, stock: StockService | None = None) -> None:
        self.stock = stock or StockService()

    async def reconcile(
        self,
        session: AsyncSession,
        *,
        item_id: int,
        location_id: int,
        actual_qty: int,
        ref: str,
    ) -> Dict[str, Any]:
        on_hand = await self.stock.get_on_hand(
            session=session, item_id=item_id, location_id=location_id
        )
        delta = int(actual_qty) - int(on_hand)

        result: Dict[str, Any] = {
            "on_hand_before": on_hand,
            "actual": int(actual_qty),
            "delta": delta,
        }
        if delta != 0:
            adj = await self.stock.adjust(
                session=session,
                item_id=item_id,
                location_id=location_id,
                delta=delta,
                reason=MovementType.COUNT,
                ref=ref,
            )
            result.update({"on_hand_after": adj.get("on_hand_after", on_hand + delta)})
        else:
            result.update({"on_hand_after": on_hand})
        return result
