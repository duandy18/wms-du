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
    """

    @staticmethod
    async def detect(session: AsyncSession, *, within_days: int = 30) -> List[Dict[str, Any]]:
        today = datetime.now().date()

        sql = text(
            """
            SELECT warehouse_id, item_id, batch_code, expiry_date
            FROM batches
            WHERE expiry_date IS NOT NULL
        """
        )

        rows = (await session.execute(sql)).mappings().all()

        result = []

        for r in rows:
            exp = r["expiry_date"]
            if exp is None:
                continue

            days_left = (exp - today).days

            if days_left <= within_days:
                result.append(
                    {
                        "warehouse_id": r["warehouse_id"],
                        "item_id": r["item_id"],
                        "batch_code": r["batch_code"],
                        "expiry_date": str(exp),
                        "days_left": days_left,
                        "risk_level": (
                            "HIGH" if days_left <= 7 else "MEDIUM" if days_left <= 14 else "LOW"
                        ),
                    }
                )

        return sorted(result, key=lambda x: x["days_left"])
