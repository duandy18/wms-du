# app/services/multi_reconcile_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MultiReconcileService:
    """
    Multi-dimension Reconcile Engine
    --------------------------------

    统一对账引擎（Phase 3.x）：
    支持 4 层维度的库存对账：

    1) movement_type 汇总差异
    2) ref 维度（单据级对账）
    3) trace_id 链路级对账
    4) 账账平衡：ledger vs stocks vs snapshot_v3

    未来可以扩展 GSI 索引/分布式校验。
    """

    # -----------------------------------------------
    # Helper：取得 ledger_cut（在某个时间点）
    # -----------------------------------------------
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
                SUM(delta) AS qty
            FROM stock_ledger
            WHERE occurred_at <= :cut
            GROUP BY 1,2,3
            HAVING SUM(delta) != 0
        """
        )
        rows = (await session.execute(stmt, {"cut": cut})).mappings().all()
        return [dict(r) for r in rows]

    # -----------------------------------------------
    # movement_type 汇总
    # -----------------------------------------------
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

    # -----------------------------------------------
    # ref（单据级）对账
    # -----------------------------------------------
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

    # -----------------------------------------------
    # trace 维度链路对账
    # -----------------------------------------------
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

    # -----------------------------------------------
    # 三账一致性（ledger_cut vs stocks vs snapshot_v3）
    # -----------------------------------------------
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
                x.ledger_qty,
                COALESCE(st.qty, 0) AS stock_qty,
                COALESCE(sn.qty_on_hand, 0) AS snapshot_qty,
                (x.ledger_qty - COALESCE(st.qty,0)) AS diff_stock,
                (x.ledger_qty - COALESCE(sn.qty_on_hand,0)) AS diff_snapshot
            FROM (
                SELECT warehouse_id, item_id, batch_code, SUM(delta) AS ledger_qty
                FROM stock_ledger
                WHERE occurred_at <= :cut
                GROUP BY 1,2,3
            ) AS x
            LEFT JOIN stocks st
                ON st.warehouse_id=x.warehouse_id
               AND st.item_id=x.item_id
               AND st.batch_code=x.batch_code
            LEFT JOIN stock_snapshots sn
                ON sn.snapshot_date = :cut::date
               AND sn.warehouse_id=x.warehouse_id
               AND sn.item_id=x.item_id
               AND sn.batch_code=x.batch_code
            ORDER BY x.warehouse_id, x.item_id, x.batch_code
        """
        )
        rows = (await session.execute(stmt, {"cut": cut})).mappings().all()
        return [dict(r) for r in rows]
