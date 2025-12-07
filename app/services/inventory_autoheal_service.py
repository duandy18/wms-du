# app/services/inventory_autoheal_service.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InventoryAutoHealService:
    @staticmethod
    async def suggest(session: AsyncSession, *, cut: str) -> Dict[str, Any]:
        sql_ledger = text(
            """
            SELECT warehouse_id, item_id, batch_code, SUM(delta) AS qty
            FROM stock_ledger
            WHERE occurred_at <= :cut
            GROUP BY 1,2,3
        """
        )
        ledger_map = {
            (row["warehouse_id"], row["item_id"], row["batch_code"]): int(row["qty"])
            for row in (await session.execute(sql_ledger, {"cut": cut})).mappings().all()
        }

        sql_stocks = text("SELECT warehouse_id, item_id, batch_code, qty FROM stocks")
        stocks_map = {
            (row["warehouse_id"], row["item_id"], row["batch_code"]): int(row["qty"])
            for row in (await session.execute(sql_stocks)).mappings().all()
        }

        suggestions = []

        all_keys = set(ledger_map.keys()) | set(stocks_map.keys())

        for key in sorted(all_keys):
            ledger_qty = ledger_map.get(key, 0)
            stocks_qty = stocks_map.get(key, 0)

            diff = ledger_qty - stocks_qty
            if diff != 0:
                suggestions.append(
                    {
                        "warehouse_id": key[0],
                        "item_id": key[1],
                        "batch_code": key[2],
                        "ledger": ledger_qty,
                        "stocks": stocks_qty,
                        "diff": diff,
                        "action": "INCREASE" if diff > 0 else "DECREASE",
                        "adjust_delta": diff,
                    }
                )

        return {"count": len(suggestions), "suggestions": suggestions}
