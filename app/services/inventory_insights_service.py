# app/services/inventory_insights_service.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class InventoryInsightsService:
    """
    Inventory Insights（库存洞察）
    -------------------------------------
    输出可用于 Dashboard 的库存健康与洞察指标集：

    - inventory_health_score      全局存量健康指数（stocks/ledger）
    - inventory_accuracy_score    ledger vs stocks 一致性
    - snapshot_accuracy_score     ledger vs snapshot_v3 一致性
    - batch_activity_30days       批次活跃指数
    - batch_risk_score            批次过期风险指数
    - warehouse_efficiency        仓库事件分布效率（出库事件占比）
    """

    @staticmethod
    async def insights(session: AsyncSession) -> Dict[str, Any]:
        # -------------------------------------------------------------------
        # 1) ledger_rows + stocks_rows — 全局结构健康
        # -------------------------------------------------------------------
        diff_sql = text(
            """
            SELECT
                (SELECT COUNT(*) FROM stock_ledger) AS ledger_rows,
                (SELECT COUNT(*) FROM stocks) AS stock_rows
        """
        )
        diff = (await session.execute(diff_sql)).mappings().first()

        ledger_rows = int(diff["ledger_rows"] or 0)
        stock_rows = int(diff["stock_rows"] or 0)

        # 健康得分：库存槽位数量 / 台账事件数量（偏低表示事件过多或库存结构异常）
        inventory_health_score = (stock_rows / ledger_rows) if ledger_rows > 0 else 1.0
        inventory_health_score = round(min(max(inventory_health_score, 0), 1), 4)

        # -------------------------------------------------------------------
        # 2) accuracy：ledger_cut vs stocks
        # -------------------------------------------------------------------
        acc_ledger_sql = text(
            """
            SELECT COUNT(*) FROM (
                SELECT
                    l.warehouse_id, l.item_id, l.batch_code,
                    SUM(l.delta) AS ledger_qty,
                    s.qty AS stock_qty
                FROM stock_ledger AS l
                LEFT JOIN stocks AS s
                  ON s.warehouse_id=l.warehouse_id
                 AND s.item_id=l.item_id
                 AND s.batch_code=l.batch_code
                GROUP BY 1,2,3, s.qty
            ) AS x
            WHERE x.ledger_qty = x.stock_qty
        """
        )
        acc_ok = int((await session.execute(acc_ledger_sql)).scalar() or 0)

        total_slot_sql = text("SELECT COUNT(*) FROM stocks")
        total_slots = int((await session.execute(total_slot_sql)).scalar() or 1)

        inventory_accuracy_score = round(acc_ok / total_slots, 4)

        # -------------------------------------------------------------------
        # 3) snapshot_accuracy：ledger vs snapshot_v3
        # -------------------------------------------------------------------
        snap_sql = text(
            """
            SELECT COUNT(*) FROM (
                SELECT
                    l.warehouse_id, l.item_id, l.batch_code,
                    SUM(l.delta) AS ledger_qty,
                    COALESCE(s.qty_on_hand, 0) AS snap_qty
                FROM stock_ledger AS l
                LEFT JOIN stock_snapshots AS s
                  ON s.warehouse_id=l.warehouse_id
                 AND s.item_id=l.item_id
                 AND s.batch_code=l.batch_code
                 AND s.snapshot_date = CURRENT_DATE
                GROUP BY 1,2,3, snap_qty
            ) AS x
            WHERE x.ledger_qty = x.snap_qty
        """
        )
        snap_ok = int((await session.execute(snap_sql)).scalar() or 0)

        snapshot_row_sql = text(
            """
            SELECT COUNT(*) FROM stock_snapshots WHERE snapshot_date = CURRENT_DATE
        """
        )
        snap_rows = int((await session.execute(snapshot_row_sql)).scalar() or 1)

        snapshot_accuracy_score = round(snap_ok / snap_rows, 4)

        # -------------------------------------------------------------------
        # 4) 批次活跃度：最近 30 天事件数量
        # -------------------------------------------------------------------
        active_sql = text(
            """
            SELECT COUNT(*) AS active_batches
            FROM stock_ledger
            WHERE occurred_at >= NOW() - INTERVAL '30 days'
        """
        )
        active_batches = int((await session.execute(active_sql)).scalar() or 0)

        # -------------------------------------------------------------------
        # 5) 批次老化风险指数 batch_risk_score
        #     - <=7 天 HIGH
        #     - <=14 天 MED
        #     - <=30 天 LOW
        # -------------------------------------------------------------------
        ageing_sql = text(
            """
            SELECT expiry_date
            FROM batches
            WHERE expiry_date IS NOT NULL
        """
        )
        rows = (await session.execute(ageing_sql)).mappings().all()

        today = datetime.now().date()
        risk_score = 0
        total_batches = 0

        for r in rows:
            exp = r["expiry_date"]
            if exp:
                total_batches += 1
                days_left = (exp - today).days
                if days_left <= 7:
                    risk_score += 3
                elif days_left <= 14:
                    risk_score += 2
                elif days_left <= 30:
                    risk_score += 1

        # 归一化
        batch_risk_score = round((risk_score / (total_batches * 3)) if total_batches > 0 else 0, 4)

        # -------------------------------------------------------------------
        # 6) 仓库效率（出库事件占比）
        # -------------------------------------------------------------------
        wh_sql = text(
            """
            SELECT
                SUM(CASE WHEN delta < 0 THEN 1 ELSE 0 END) AS outbound_events,
                COUNT(*) AS total_events
            FROM stock_ledger
        """
        )
        wh = (await session.execute(wh_sql)).mappings().first()

        warehouse_efficiency = round((wh["outbound_events"] or 0) / (wh["total_events"] or 1), 4)

        # -------------------------------------------------------------------
        # 结果整合
        # -------------------------------------------------------------------
        return {
            "inventory_health_score": inventory_health_score,
            "inventory_accuracy_score": inventory_accuracy_score,
            "snapshot_accuracy_score": snapshot_accuracy_score,
            "batch_activity_30days": active_batches,
            "batch_risk_score": batch_risk_score,
            "warehouse_efficiency": warehouse_efficiency,
        }
