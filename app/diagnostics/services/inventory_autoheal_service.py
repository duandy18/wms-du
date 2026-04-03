# app/diagnostics/services/inventory_autoheal_service.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InventoryAutoHealService:
    """
    Phase 4E（真收口）：
    - 主对账基准：ledger vs stocks_lot（lot-world 读锚点）
    - 禁止读取 legacy stocks（不做 shadow 观测，不允许双余额源）
    """

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
            (int(row["warehouse_id"]), int(row["item_id"]), row.get("batch_code")): int(row["qty"])
            for row in (await session.execute(sql_ledger, {"cut": cut})).mappings().all()
        }

        # 主读锚点：stocks_lot（聚合到 item + warehouse）
        sql_lot = text(
            """
            SELECT warehouse_id, item_id, COALESCE(SUM(qty), 0) AS qty
            FROM stocks_lot
            GROUP BY 1,2
            """
        )
        lot_map = {
            (int(row["warehouse_id"]), int(row["item_id"]), None): int(row["qty"])
            for row in (await session.execute(sql_lot)).mappings().all()
        }

        suggestions = []

        # ledger_map 仍按 batch_code 维度，而 lot_map 按 (wh,item) 聚合：
        # - 主建议以 (wh,item) 聚合后的 ledger_total vs lot_total 对账
        ledger_total_by_item: Dict[tuple[int, int], int] = {}
        for (w, i, _bc), q in ledger_map.items():
            k = (w, i)
            ledger_total_by_item[k] = int(ledger_total_by_item.get(k, 0)) + int(q)

        lot_total_by_item = {(w, i): int(q) for (w, i, _none), q in lot_map.items()}

        all_item_keys = set(ledger_total_by_item.keys()) | set(lot_total_by_item.keys())

        for (w, i) in sorted(all_item_keys):
            ledger_qty = int(ledger_total_by_item.get((w, i), 0))
            lot_qty = int(lot_total_by_item.get((w, i), 0))

            diff = ledger_qty - lot_qty
            if diff != 0:
                suggestions.append(
                    {
                        "warehouse_id": w,
                        "item_id": i,
                        "batch_code": None,  # Phase 4E：主建议不按 batch_code
                        "ledger": ledger_qty,
                        "stocks_lot": lot_qty,
                        # Phase 4E：不再读 legacy stocks；保留字段名避免上游 KeyError
                        "shadow_stocks_total": None,
                        "diff": diff,
                        "action": "INCREASE" if diff > 0 else "DECREASE",
                        "adjust_delta": diff,
                    }
                )

        return {"count": len(suggestions), "suggestions": suggestions}
