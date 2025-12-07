# app/services/inventory_predict_service.py
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
    """

    @staticmethod
    async def predict(
        session: AsyncSession,
        *,
        item_id: int,
        warehouse_id: int,
        days: int = 7,
    ) -> Dict[str, Any]:
        # 当前数量
        rs = await session.execute(
            text(
                """
                SELECT qty
                FROM stocks
                WHERE warehouse_id=:w AND item_id=:i
                LIMIT 1
            """
            ),
            {"w": warehouse_id, "i": item_id},
        )
        row = rs.mappings().first()
        current_qty = int(row["qty"]) if row else 0

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
            {"w": warehouse_id, "i": item_id},
        )

        outbound_30 = -int(rs.scalar() or 0)
        avg_daily = outbound_30 / 30.0

        future_qty = int(current_qty - avg_daily * days)

        return {
            "warehouse_id": warehouse_id,
            "item_id": item_id,
            "current_qty": current_qty,
            "avg_daily_outbound": avg_daily,
            "predicted_qty": future_qty,
            "days": days,
            "risk": "OOS" if future_qty <= 0 else "SAFE",
        }
