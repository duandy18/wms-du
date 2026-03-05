# app/services/snapshot_v3_service.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotV3Service:
    """
    Snapshot v3：台账驱动快照引擎（Stage C.2：以 stock_snapshots.qty 为事实列）。

    Phase 3 终态（lot-only）：
    - 快照 grain： (snapshot_date, warehouse_id, item_id, lot_id)
    - 台账聚合维度： (warehouse_id, item_id, lot_id)
    - batch_code 仅为展示码（lots.lot_code），不参与任何维度事实/聚合键
    """

    @staticmethod
    async def snapshot_cut(
        session: AsyncSession,
        *,
        at: datetime,
    ) -> Dict[str, Any]:
        """
        生成 cut（<= at）的台账聚合结果（TEMP TABLE），用于审计/调试。

        注意：
        - 维度事实为 lot_id
        - batch_code 仅为展示：lots.lot_code（可能为 NULL）
        """
        await session.execute(text("DROP TABLE IF EXISTS snapshot_cut_result"))
        await session.execute(
            text(
                """
                CREATE TEMP TABLE snapshot_cut_result AS
                SELECT
                  l.warehouse_id,
                  l.item_id,
                  l.lot_id,
                  lo.lot_code AS batch_code,
                  SUM(l.delta) AS qty
                FROM stock_ledger l
                JOIN lots lo ON lo.id = l.lot_id
                WHERE l.occurred_at <= :at
                GROUP BY l.warehouse_id, l.item_id, l.lot_id, lo.lot_code
                HAVING SUM(l.delta) != 0;
                """
            ),
            {"at": at},
        )
        summary = (
            (
                await session.execute(
                    text("SELECT COUNT(*) AS slots, COALESCE(SUM(qty),0) AS total_qty FROM snapshot_cut_result")
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
        """
        从 stock_ledger 重建某日快照。

        - snapshot_date 取其 date 部分 d
        - cut_to = d+1 day 00:00 UTC（occurred_at < cut_to）
        - 维度事实为 lot_id
        - qty_available = qty（无预占语义）
        - qty_allocated = 0
        """
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
                    lot_id,
                    qty,
                    qty_available,
                    qty_allocated
                )
                SELECT
                    :d AS snapshot_date,
                    l.warehouse_id,
                    l.item_id,
                    l.lot_id,
                    SUM(l.delta) AS qty,
                    SUM(l.delta) AS qty_available,
                    0 AS qty_allocated
                FROM stock_ledger l
                WHERE l.occurred_at < :cut_to
                GROUP BY l.warehouse_id, l.item_id, l.lot_id
                HAVING SUM(l.delta) != 0;
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
        Phase 4E 审计对账（真收口，lot-only）：

        - ledger_qty：来自 stock_ledger（<= cut）按 (warehouse_id,item_id,lot_id) 聚合
        - snapshot_qty：来自 stock_snapshots（当日）按 (warehouse_id,item_id,lot_id)
        - stocks_lot_qty：来自 stocks_lot（主余额源）按 (warehouse_id,item_id,lot_id)

        规则：
        - diff 以 ledger 为锚，对 snapshot 与 stocks_lot 同时给出差异
        - batch_code 仅为展示：lots.lot_code
        """
        cut_ts: datetime = snapshot_date
        d: date = snapshot_date.date()

        sql = """
        WITH x AS (
            SELECT
                l.warehouse_id,
                l.item_id,
                l.lot_id,
                lo.lot_code AS batch_code,
                SUM(l.delta) AS ledger_qty
            FROM stock_ledger l
            JOIN lots lo ON lo.id = l.lot_id
            WHERE l.occurred_at <= :cut
            GROUP BY l.warehouse_id, l.item_id, l.lot_id, lo.lot_code
        ),
        lot_agg AS (
            SELECT
                s.warehouse_id,
                s.item_id,
                s.lot_id,
                COALESCE(SUM(s.qty), 0) AS qty
            FROM stocks_lot s
            GROUP BY s.warehouse_id, s.item_id, s.lot_id
        )
        SELECT
            x.warehouse_id,
            x.item_id,
            x.lot_id,
            x.batch_code,
            x.ledger_qty,
            COALESCE(sn.qty, 0) AS snapshot_qty,
            COALESCE(la.qty, 0) AS stocks_lot_qty,
            (x.ledger_qty - COALESCE(sn.qty, 0)) AS diff_snapshot,
            (x.ledger_qty - COALESCE(la.qty, 0)) AS diff_stocks_lot
        FROM x
        LEFT JOIN stock_snapshots sn
            ON sn.snapshot_date = :date
           AND sn.warehouse_id  = x.warehouse_id
           AND sn.item_id       = x.item_id
           AND sn.lot_id        = x.lot_id
        LEFT JOIN lot_agg la
            ON la.warehouse_id = x.warehouse_id
           AND la.item_id      = x.item_id
           AND la.lot_id       = x.lot_id
        ORDER BY x.warehouse_id, x.item_id, x.lot_id;
        """

        rows = (await session.execute(text(sql), {"cut": cut_ts, "date": d})).mappings().all()
        return {"rows": [dict(r) for r in rows]}
