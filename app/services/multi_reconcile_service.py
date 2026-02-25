# app/services/multi_reconcile_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_NULL_BATCH_KEY = "__NULL_BATCH__"


class MultiReconcileService:
    """
    Multi-dimension Reconcile Engine
    --------------------------------

    Phase 4B-3（切读到 lot）：
    - three_books_compare：stocks 侧改为 stocks_lot
    - batch_code 展示值改为 lots.lot_code
    """

    @staticmethod
    async def _ledger_cut(
        session: AsyncSession,
        *,
        cut: datetime,
    ) -> List[Dict[str, Any]]:
        stmt = text(
            """
            SELECT
                warehouse_id,
                item_id,
                batch_code,
                batch_code_key,
                SUM(delta) AS qty
            FROM stock_ledger
            WHERE occurred_at <= :cut
            GROUP BY 1,2,3,4
            HAVING SUM(delta) != 0
        """
        )
        rows = (await session.execute(stmt, {"cut": cut})).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def movement_type_summary(
        session: AsyncSession,
        *,
        time_from: datetime,
        time_to: datetime,
    ) -> Dict[str, Any]:
        stmt = text(
            """
            SELECT movement_type, COUNT(*) AS cnt, SUM(delta) AS total_delta
            FROM (
                SELECT
                    CASE
                      WHEN reason IN ('RECEIPT','INBOUND','INBOUND_RECEIPT') THEN 'INBOUND'
                      WHEN reason IN ('SHIP','SHIPMENT','OUTBOUND_SHIP','OUTBOUND_COMMIT') THEN 'OUTBOUND'
                      WHEN reason IN ('COUNT','STOCK_COUNT','INVENTORY_COUNT') THEN 'COUNT'
                      WHEN reason IN ('ADJUST','ADJUSTMENT','MANUAL_ADJUST') THEN 'ADJUST'
                      WHEN reason IN ('RETURN','RMA','INBOUND_RETURN') THEN 'RETURN'
                      ELSE 'UNKNOWN'
                    END AS movement_type,
                    delta
                FROM stock_ledger
                WHERE occurred_at >= :t1 AND occurred_at <= :t2
            ) AS x
            GROUP BY movement_type
        """
        )
        rs = (await session.execute(stmt, {"t1": time_from, "t2": time_to})).mappings().all()
        return {
            r["movement_type"]: {
                "count": int(r["cnt"]),
                "total_delta": int(r["total_delta"]),
            }
            for r in rs
        }

    @staticmethod
    async def ref_summary(
        session: AsyncSession,
        *,
        time_from: datetime,
        time_to: datetime,
    ) -> List[Dict[str, Any]]:
        stmt = text(
            """
            SELECT ref, SUM(delta) AS total_delta, COUNT(*) AS cnt
            FROM stock_ledger
            WHERE occurred_at >= :t1 AND occurred_at <= :t2
            GROUP BY ref
            ORDER BY ref
        """
        )
        rows = (await session.execute(stmt, {"t1": time_from, "t2": time_to})).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def trace_summary(
        session: AsyncSession,
        *,
        time_from: datetime,
        time_to: datetime,
    ) -> List[Dict[str, Any]]:
        stmt = text(
            """
            SELECT trace_id, SUM(delta) AS total_delta, COUNT(*) AS cnt
            FROM stock_ledger
            WHERE trace_id IS NOT NULL
              AND occurred_at >= :t1 AND occurred_at <= :t2
            GROUP BY trace_id
            ORDER BY trace_id
        """
        )
        rows = (await session.execute(stmt, {"t1": time_from, "t2": time_to})).mappings().all()
        return [dict(r) for r in rows]

    @staticmethod
    async def three_books_compare(
        session: AsyncSession,
        *,
        cut: datetime,
    ) -> List[Dict[str, Any]]:
        stmt = text(
            """
            SELECT
                x.warehouse_id,
                x.item_id,
                x.batch_code,
                x.batch_code_key,
                x.ledger_qty,
                COALESCE(st.qty, 0) AS stock_qty,
                COALESCE(sn.qty, 0) AS snapshot_qty,
                (x.ledger_qty - COALESCE(st.qty,0)) AS diff_stock,
                (x.ledger_qty - COALESCE(sn.qty,0)) AS diff_snapshot
            FROM (
                SELECT
                    l.warehouse_id,
                    l.item_id,
                    lo.lot_code AS batch_code,
                    COALESCE(lo.lot_code, :null_key) AS batch_code_key,
                    SUM(l.delta) AS ledger_qty
                FROM stock_ledger l
                LEFT JOIN lots lo
                  ON lo.id = l.lot_id
                WHERE l.occurred_at <= :cut
                GROUP BY 1,2,3,4
            ) AS x
            LEFT JOIN (
                SELECT
                  s.warehouse_id,
                  s.item_id,
                  COALESCE(lo.lot_code, :null_key) AS batch_code_key,
                  SUM(s.qty)::integer AS qty
                FROM stocks_lot s
                LEFT JOIN lots lo
                  ON lo.id = s.lot_id
                GROUP BY 1,2,3
            ) st
                ON st.warehouse_id = x.warehouse_id
               AND st.item_id      = x.item_id
               AND st.batch_code_key = x.batch_code_key
            LEFT JOIN stock_snapshots sn
                ON sn.snapshot_date = :cut::date
               AND sn.warehouse_id  = x.warehouse_id
               AND sn.item_id       = x.item_id
               AND sn.batch_code_key = x.batch_code_key
            ORDER BY x.warehouse_id, x.item_id, x.batch_code_key
        """
        )
        rows = (await session.execute(stmt, {"cut": cut, "null_key": _NULL_BATCH_KEY})).mappings().all()
        return [dict(r) for r in rows]
