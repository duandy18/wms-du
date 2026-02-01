# app/services/snapshot_v3_service.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotV3Service:
    """
    Snapshot v3：台账驱动快照引擎。
    """

    @staticmethod
    async def snapshot_cut(
        session: AsyncSession,
        *,
        at: datetime,
    ) -> Dict[str, Any]:
        await session.execute(text("DROP TABLE IF EXISTS snapshot_cut_result"))
        await session.execute(
            text(
                """
                CREATE TEMP TABLE snapshot_cut_result AS
                SELECT
                  warehouse_id,
                  item_id,
                  batch_code,
                  SUM(delta) AS qty
                FROM stock_ledger
                WHERE occurred_at <= :at
                GROUP BY warehouse_id, item_id, batch_code
                HAVING SUM(delta) != 0;
                """
            ),
            {"at": at},
        )
        summary = (
            (await session.execute(text("SELECT COUNT(*) AS slots, COALESCE(SUM(qty),0) AS total_qty FROM snapshot_cut_result")))
            .mappings()
            .first()
        )
        return {"slot_count": int(summary["slots"]), "total_qty": int(summary["total_qty"])}

    @staticmethod
    async def rebuild_snapshot_from_ledger(
        session: AsyncSession,
        *,
        snapshot_date: datetime,
    ) -> Dict[str, Any]:
        d: date = snapshot_date.date()
        cut_to = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)

        await session.execute(text("DELETE FROM stock_snapshots WHERE snapshot_date = :d"), {"d": d})

        # batch_code_key 为 generated column，INSERT 不写它
        await session.execute(
            text(
                """
                INSERT INTO stock_snapshots (
                    snapshot_date,
                    warehouse_id,
                    item_id,
                    batch_code,
                    qty_on_hand,
                    qty_available,
                    qty_allocated
                )
                SELECT
                    :d AS snapshot_date,
                    warehouse_id,
                    item_id,
                    batch_code,
                    SUM(delta) AS qty_on_hand,
                    SUM(delta) AS qty_available,
                    0 AS qty_allocated
                FROM stock_ledger
                WHERE occurred_at < :cut_to
                GROUP BY warehouse_id, item_id, batch_code
                HAVING SUM(delta) != 0;
                """
            ),
            {"d": d, "cut_to": cut_to},
        )

        summary = (
            (
                await session.execute(
                    text(
                        """
                        SELECT COUNT(*) AS slots, COALESCE(SUM(qty_on_hand),0) AS total_qty
                        FROM stock_snapshots
                        WHERE snapshot_date = :d
                        """
                    ),
                    {"d": d},
                )
            )
            .mappings()
            .first()
        )
        return {"snapshot_date": str(d), "slot_count": int(summary["slots"]), "total_qty": int(summary["total_qty"])}

    @staticmethod
    async def compare_snapshot(
        session: AsyncSession,
        *,
        snapshot_date: datetime,
    ) -> Dict[str, Any]:
        cut_ts: datetime = snapshot_date
        d: date = snapshot_date.date()

        sql = """
        SELECT
            x.warehouse_id,
            x.item_id,
            x.batch_code,
            x.batch_code_key,
            x.ledger_qty,
            COALESCE(s.qty_on_hand, 0) AS snapshot_qty,
            COALESCE(st.qty, 0) AS stock_qty,
            (x.ledger_qty - COALESCE(s.qty_on_hand, 0)) AS diff_snapshot,
            (x.ledger_qty - COALESCE(st.qty, 0)) AS diff_stock
        FROM (
            SELECT
                warehouse_id,
                item_id,
                batch_code,
                COALESCE(batch_code, '__NULL_BATCH__') AS batch_code_key,
                SUM(delta) AS ledger_qty
            FROM stock_ledger
            WHERE occurred_at <= :cut
            GROUP BY warehouse_id, item_id, batch_code
        ) AS x
        LEFT JOIN stock_snapshots s
            ON s.snapshot_date   = :date
           AND s.warehouse_id    = x.warehouse_id
           AND s.item_id         = x.item_id
           AND s.batch_code_key  = x.batch_code_key
        LEFT JOIN stocks st
            ON st.warehouse_id   = x.warehouse_id
           AND st.item_id        = x.item_id
           AND st.batch_code_key = x.batch_code_key
        ORDER BY x.warehouse_id, x.item_id, x.batch_code_key;
        """

        rows = (await session.execute(text(sql), {"cut": cut_ts, "date": d})).mappings().all()
        return {"rows": [dict(r) for r in rows]}
