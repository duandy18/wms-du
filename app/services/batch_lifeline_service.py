# app/services/batch_lifeline_service.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class BatchLifelineService:
    """
    批次生命周期：
    inbound → adjust → pick → ship → count → ledger → stocks/snapshot
    """

    @staticmethod
    async def load_lifeline(
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        batch_code: str,
    ) -> Dict[str, Any]:
        base = {
            "warehouse_id": warehouse_id,
            "item_id": item_id,
            "batch_code": batch_code,
        }

        # ledger timeline
        rs = await session.execute(
            text(
                """
                SELECT id, occurred_at, reason, delta, after_qty,
                       trace_id, ref
                FROM stock_ledger
                WHERE warehouse_id=:w AND item_id=:i AND batch_code=:b
                ORDER BY occurred_at ASC, id ASC
            """
            ),
            {"w": warehouse_id, "i": item_id, "b": batch_code},
        )
        base["ledger"] = [dict(r) for r in rs.mappings().all()]

        # current stock
        rs = await session.execute(
            text(
                """
                SELECT qty
                FROM stocks
                WHERE warehouse_id=:w AND item_id=:i AND batch_code=:b
            """
            ),
            {"w": warehouse_id, "i": item_id, "b": batch_code},
        )
        row = rs.mappings().first()
        base["current_stock"] = int(row["qty"]) if row else 0

        return base
