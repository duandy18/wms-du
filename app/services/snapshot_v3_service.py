# app/services/snapshot_v3_service.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotV3Service:
    """
    Snapshot v3：台账驱动快照引擎（Stage C.2：以 stock_snapshots.qty 为事实列）。
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
            (
                await session.execute(
                    text(
                        "SELECT COUNT(*) AS slots, COALESCE(SUM(qty),0) AS total_qty FROM snapshot_cut_result"
                    )
                )
            )
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

        await session.execute(
            text(
                """
                INSERT INTO stock_snapshots (
                    snapshot_date,
                    warehouse_id,
                    item_id,
                    batch_code,
                    qty,
                    qty_available,
                    qty_allocated
                )
                SELECT
                    :d AS snapshot_date,
                    warehouse_id,
                    item_id,
                    batch_code,
                    SUM(delta) AS qty,
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
                        SELECT COUNT(*) AS slots, COALESCE(SUM(qty),0) AS total_qty
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
        """
        Phase 4E 审计对账（真收口）：

        - ledger_qty：来自 stock_ledger（<= cut）
        - snapshot_qty：来自 stock_snapshots（当日）
        - stocks_lot_qty：来自 stocks_lot（主余额源，lot-world）

        规则：
        - 不允许读取 legacy stocks
        - diff 以 ledger 为锚，对 snapshot 与 stocks_lot 同时给出差异
        """
        cut_ts: datetime = snapshot_date
        d: date = snapshot_date.date()

        sql = """
        WITH x AS (
            SELECT
                warehouse_id,
                item_id,
                batch_code,
                COALESCE(batch_code, '__NULL_BATCH__') AS batch_code_key,
                SUM(delta) AS ledger_qty
            FROM stock_ledger
            WHERE occurred_at <= :cut
            GROUP BY warehouse_id, item_id, batch_code
        ),
        lot_agg AS (
            SELECT
                s.warehouse_id,
                s.item_id,
                COALESCE(lo.lot_code, '__NULL_BATCH__') AS batch_code_key,
                COALESCE(SUM(s.qty), 0) AS qty
            FROM stocks_lot s
            LEFT JOIN lots lo ON lo.id = s.lot_id
            GROUP BY 1,2,3
        )
        SELECT
            x.warehouse_id,
            x.item_id,
            x.batch_code,
            x.batch_code_key,
            x.ledger_qty,
            COALESCE(sn.qty, 0) AS snapshot_qty,
            COALESCE(la.qty, 0) AS stocks_lot_qty,
            (x.ledger_qty - COALESCE(sn.qty, 0)) AS diff_snapshot,
            (x.ledger_qty - COALESCE(la.qty, 0)) AS diff_stocks_lot
        FROM x
        LEFT JOIN stock_snapshots sn
            ON sn.snapshot_date   = :date
           AND sn.warehouse_id    = x.warehouse_id
           AND sn.item_id         = x.item_id
           AND sn.batch_code_key  = x.batch_code_key
        LEFT JOIN lot_agg la
            ON la.warehouse_id   = x.warehouse_id
           AND la.item_id        = x.item_id
           AND la.batch_code_key = x.batch_code_key
        ORDER BY x.warehouse_id, x.item_id, x.batch_code_key;
        """

        rows = (await session.execute(text(sql), {"cut": cut_ts, "date": d})).mappings().all()
        return {"rows": [dict(r) for r in rows]}
