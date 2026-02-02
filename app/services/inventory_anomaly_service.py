# app/services/inventory_anomaly_service.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InventoryAnomalyService:
    @staticmethod
    async def detect(session: AsyncSession, *, cut: str) -> Dict[str, Any]:
        ledger_sql = text(
            """
            SELECT warehouse_id, item_id, batch_code, SUM(delta) AS qty
            FROM stock_ledger
            WHERE occurred_at <= :cut
            GROUP BY 1,2,3
        """
        )
        ledger_rows = (await session.execute(ledger_sql, {"cut": cut})).mappings().all()

        stocks_sql = text(
            """
            SELECT warehouse_id, item_id, batch_code, qty
            FROM stocks
        """
        )
        stocks_rows = (await session.execute(stocks_sql)).mappings().all()

        # ✅ Stage C.2-1：snapshot 新事实列为 qty（不再读 qty_on_hand）
        snap_sql = text(
            """
            SELECT warehouse_id, item_id, batch_code, qty
            FROM stock_snapshots
            WHERE snapshot_date = :d
        """
        )
        snap_rows = (await session.execute(snap_sql, {"d": cut.split("T")[0]})).mappings().all()

        def to_map(rows, key, val):
            mapping: dict[tuple[int, int, str], int] = {}
            for row in rows:
                k = (row["warehouse_id"], row["item_id"], row["batch_code"])
                mapping[k] = int(row[val])
            return mapping

        ledger_map = to_map(ledger_rows, "batch_code", "qty")
        stocks_map = to_map(stocks_rows, "batch_code", "qty")
        snapshot_map = to_map(snap_rows, "batch_code", "qty")

        anomalies_ledger_stocks = []
        anomalies_ledger_snapshot = []
        anomalies_stocks_snapshot = []

        all_keys = set(ledger_map.keys()) | set(stocks_map.keys()) | set(snapshot_map.keys())

        for key in sorted(all_keys):
            ledger_qty = ledger_map.get(key, 0)
            stocks_qty = stocks_map.get(key, 0)
            snapshot_qty = snapshot_map.get(key, 0)

            if ledger_qty != stocks_qty:
                anomalies_ledger_stocks.append(
                    {
                        "wh": key[0],
                        "item": key[1],
                        "batch": key[2],
                        "ledger": ledger_qty,
                        "stocks": stocks_qty,
                        "diff": ledger_qty - stocks_qty,
                    }
                )
            if ledger_qty != snapshot_qty:
                anomalies_ledger_snapshot.append(
                    {
                        "wh": key[0],
                        "item": key[1],
                        "batch": key[2],
                        "ledger": ledger_qty,
                        "snapshot": snapshot_qty,
                        "diff": ledger_qty - snapshot_qty,
                    }
                )
            if stocks_qty != snapshot_qty:
                anomalies_stocks_snapshot.append(
                    {
                        "wh": key[0],
                        "item": key[1],
                        "batch": key[2],
                        "stocks": stocks_qty,
                        "snapshot": snapshot_qty,
                        "diff": stocks_qty - snapshot_qty,
                    }
                )

        return {
            "ledger_vs_stocks": anomalies_ledger_stocks,
            "ledger_vs_snapshot": anomalies_ledger_snapshot,
            "stocks_vs_snapshot": anomalies_stocks_snapshot,
        }
