# app/diagnostics/services/inventory_anomaly_service.py
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InventoryAnomalyService:
    @staticmethod
    async def detect(session: AsyncSession, *, cut: str) -> Dict[str, Any]:
        # ledger：lot-only，展示码来自 lots.lot_code
        ledger_sql = text(
            """
            SELECT
              l.warehouse_id,
              l.item_id,
              l.lot_id,
              lo.lot_code AS batch_code,
              SUM(l.delta) AS qty
            FROM stock_ledger l
            JOIN lots lo
              ON lo.id = l.lot_id
            WHERE l.occurred_at <= :cut
            GROUP BY 1,2,3,4
        """
        )
        ledger_rows = (await session.execute(ledger_sql, {"cut": cut})).mappings().all()

        # stocks_lot：lot-only，展示码来自 lots.lot_code
        stocks_lot_sql = text(
            """
            SELECT
              s.warehouse_id,
              s.item_id,
              s.lot_id,
              lo.lot_code AS batch_code,
              SUM(s.qty)::integer AS qty
            FROM stocks_lot s
            JOIN lots lo
              ON lo.id = s.lot_id
            GROUP BY 1,2,3,4
        """
        )
        stocks_lot_rows = (await session.execute(stocks_lot_sql)).mappings().all()

        # snapshot：lot-only（stock_snapshots 无 batch_code；展示码 join lots）
        snap_sql = text(
            """
            SELECT
              sn.warehouse_id,
              sn.item_id,
              sn.lot_id,
              lo.lot_code AS batch_code,
              sn.qty
            FROM stock_snapshots sn
            JOIN lots lo
              ON lo.id = sn.lot_id
            WHERE sn.snapshot_date = :d
        """
        )
        snap_rows = (await session.execute(snap_sql, {"d": cut.split("T")[0]})).mappings().all()

        def to_map(rows, val_key: str) -> dict[tuple[int, int, int], tuple[int, str | None]]:
            mapping: dict[tuple[int, int, int], tuple[int, str | None]] = {}
            for row in rows:
                k = (int(row["warehouse_id"]), int(row["item_id"]), int(row["lot_id"]))
                mapping[k] = (int(row.get(val_key) or 0), row.get("batch_code"))
            return mapping

        ledger_map = to_map(ledger_rows, "qty")
        stocks_lot_map = to_map(stocks_lot_rows, "qty")
        snapshot_map = to_map(snap_rows, "qty")

        anomalies_ledger_stocks_lot = []
        anomalies_ledger_snapshot = []
        anomalies_stocks_lot_snapshot = []

        all_keys = set(ledger_map.keys()) | set(stocks_lot_map.keys()) | set(snapshot_map.keys())

        for key in sorted(all_keys):
            ledger_qty, bc1 = ledger_map.get(key, (0, None))
            stocks_lot_qty, bc2 = stocks_lot_map.get(key, (0, None))
            snapshot_qty, bc3 = snapshot_map.get(key, (0, None))
            batch_code = bc1 if bc1 is not None else (bc2 if bc2 is not None else bc3)

            if ledger_qty != stocks_lot_qty:
                anomalies_ledger_stocks_lot.append(
                    {
                        "wh": key[0],
                        "item": key[1],
                        "lot_id": key[2],
                        "batch": batch_code,
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
                        "lot_id": key[2],
                        "batch": batch_code,
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
                        "lot_id": key[2],
                        "batch": batch_code,
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
