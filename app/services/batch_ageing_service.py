# app/services/batch_ageing_service.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class BatchAgeingService:
    """
    Batch Ageing Intelligence
    -------------------------
    自动检测批次老化（near expiry）。

    Phase 4E（真收口）：
    - 禁止读取 legacy 批次表
    - 批次属性来自 lots（expiry_date / lot_code）
    - 只关注仍有库存的批次：stocks_lot.qty > 0
    """

    @staticmethod
    async def detect(session: AsyncSession, *, within_days: int = 30) -> List[Dict[str, Any]]:
        today = datetime.now().date()

        sql = text(
            """
            SELECT
                s.warehouse_id,
                s.item_id,
                lo.lot_code AS batch_code,
                lo.expiry_date,
                COALESCE(SUM(s.qty), 0) AS qty
            FROM stocks_lot s
            JOIN lots lo ON lo.id = s.lot_id
            WHERE lo.expiry_date IS NOT NULL
              AND s.qty > 0
            GROUP BY s.warehouse_id, s.item_id, lo.lot_code, lo.expiry_date
            """
        )

        rows = (await session.execute(sql)).mappings().all()

        result: List[Dict[str, Any]] = []

        for r in rows:
            exp = r["expiry_date"]
            if exp is None:
                continue

            days_left = (exp - today).days

            if days_left <= within_days:
                result.append(
                    {
                        "warehouse_id": int(r["warehouse_id"]),
                        "item_id": int(r["item_id"]),
                        "batch_code": r["batch_code"],
                        "expiry_date": str(exp),
                        "days_left": int(days_left),
                        "risk_level": "HIGH" if days_left <= 7 else "MEDIUM" if days_left <= 14 else "LOW",
                        "qty": int(r["qty"] or 0),
                    }
                )

        return sorted(result, key=lambda x: x["days_left"])
