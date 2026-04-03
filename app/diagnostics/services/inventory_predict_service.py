# app/diagnostics/services/inventory_predict_service.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InventoryPredictService:
    """
    Inventory Prediction
    --------------------
    基于过去 7/14/30 天的出库行为预测未来库存。

    简化模型（极稳健）：
      future_qty = current_qty - avg_daily_outbound * N_days

    Phase 4B-3（切读到 lot）：
      current_qty = SUM(stocks_lot.qty)
    """

    @staticmethod
    async def predict(
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,
        days: int = 7,
    ) -> Dict[str, Any]:
        # 当前数量（lot 维度余额聚合）
        rs = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(qty), 0) AS qty
                FROM stocks_lot
                WHERE warehouse_id=:w AND item_id=:i
            """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
        current_qty = int(rs.scalar() or 0)

        # 出库量（最近 30 天）
        rs = await session.execute(
            text(
                """
                SELECT SUM(delta) AS outbound
                FROM stock_ledger
                WHERE warehouse_id=:w AND item_id=:i
                  AND delta < 0
                  AND occurred_at >= NOW() - INTERVAL '30 days'
            """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )

        outbound_30 = -int(rs.scalar() or 0)
        avg_daily = outbound_30 / 30.0

        future_qty = int(current_qty - avg_daily * int(days))

        return {
            "warehouse_id": int(warehouse_id),
            "item_id": int(item_id),
            "current_qty": int(current_qty),
            "avg_daily_outbound": avg_daily,
            "predicted_qty": int(future_qty),
            "days": int(days),
            "risk": "OOS" if future_qty <= 0 else "SAFE",
        }
