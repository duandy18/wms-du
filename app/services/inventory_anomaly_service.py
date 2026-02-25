# app/services/inventory_anomaly_service.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InventoryAnomalyService:
    @staticmethod
    async def detect(session: AsyncSession, *, cut: str) -> Dict[str, Any]:
        # ledger：用 lot_code 作为展示 batch_code（Phase 4B-3）
        ledger_sql = text(
            """
            SELECT
              l.warehouse_id,
              l.item_id,
              lo.lot_code AS batch_code,
              SUM(l.delta) AS qty
            FROM stock_ledger l
            LEFT JOIN lots lo
              ON lo.id = l.lot_id
            WHERE l.occurred_at <= :cut
            GROUP BY 1,2,3
        """
        )
        ledger_rows = (await session.execute(ledger_sql, {"cut": cut})).mappings().all()

        # stocks_lot：以 lots.lot_code 作为展示 batch_code
        stocks_lot_sql = text(
            """
            SELECT
              s.warehouse_id,
              s.item_id,
              lo.lot_code AS batch_code,
              SUM(s.qty)::integer AS qty
            FROM stocks_lot s
            LEFT JOIN lots lo
              ON lo.id = s.lot_id
            GROUP BY 1,2,3
        """
        )
        stocks_lot_rows = (await session.execute(stocks_lot_sql)).mappings().all()

        # ✅ Stage C.2-1：snapshot 新事实列为 qty（不再读 qty_on_hand）
        # 注意：snapshot 的 batch_code 已在 Phase 4B-3 的 fallback 逻辑中写入 lots.lot_code（展示码）
        snap_sql = text(
            """
            SELECT warehouse_id, item_id, batch_code, qty
            FROM stock_snapshots
            WHERE snapshot_date = :d
        """
        )
        snap_rows = (await session.execute(snap_sql, {"d": cut.split("T")[0]})).mappings().all()

        def to_map(rows, val_key: str) -> dict[tuple[int, int, str | None], int]:
            mapping: dict[tuple[int, int, str | None], int] = {}
            for row in rows:
                k = (int(row["warehouse_id"]), int(row["item_id"]), row.get("batch_code"))
                mapping[k] = int(row.get(val_key) or 0)
            return mapping

        ledger_map = to_map(ledger_rows, "qty")
        stocks_lot_map = to_map(stocks_lot_rows, "qty")
        snapshot_map = to_map(snap_rows, "qty")

        anomalies_ledger_stocks_lot = []
        anomalies_ledger_snapshot = []
        anomalies_stocks_lot_snapshot = []

        all_keys = set(ledger_map.keys()) | set(stocks_lot_map.keys()) | set(snapshot_map.keys())

        for key in sorted(all_keys):
            ledger_qty = int(ledger_map.get(key, 0))
            stocks_lot_qty = int(stocks_lot_map.get(key, 0))
            snapshot_qty = int(snapshot_map.get(key, 0))

            if ledger_qty != stocks_lot_qty:
                anomalies_ledger_stocks_lot.append(
                    {
                        "wh": key[0],
                        "item": key[1],
                        "batch": key[2],
                        "ledger": ledger_qty,
                        "stocks_lot": stocks_lot_qty,
                        "diff": ledger_qty - stocks_lot_qty,
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
            if stocks_lot_qty != snapshot_qty:
                anomalies_stocks_lot_snapshot.append(
                    {
                        "wh": key[0],
                        "item": key[1],
                        "batch": key[2],
                        "stocks_lot": stocks_lot_qty,
                        "snapshot": snapshot_qty,
                        "diff": stocks_lot_qty - snapshot_qty,
                    }
                )

        return {
            "ledger_vs_stocks_lot": anomalies_ledger_stocks_lot,
            "ledger_vs_snapshot": anomalies_ledger_snapshot,
            "stocks_lot_vs_snapshot": anomalies_stocks_lot_snapshot,
        }
