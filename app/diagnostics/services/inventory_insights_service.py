# app/diagnostics/services/inventory_insights_service.py
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

    Phase M-2 / Phase 3（lot-only）：
    - stock_rows 统计 stocks_lot
    - ledger vs stock 一致性：使用 lot_id 维度对齐
    - 过期风险：从 lots.expiry_date 读取 canonical 到期日期

    ✅ 运维口径（封板）：
    - 默认只统计 PROD（排除 DEFAULT Test Set 商品）
    """

    @staticmethod
    async def insights(session: AsyncSession) -> Dict[str, Any]:
        default_set_cte = """
        WITH default_set AS (
            SELECT id AS set_id
              FROM item_test_sets
             WHERE code = 'DEFAULT'
             LIMIT 1
        )
        """

        # 1) ledger_rows + stock_rows（PROD-only）
        diff_sql = text(
            default_set_cte
            + """
            SELECT
                (
                    SELECT COUNT(*)
                      FROM stock_ledger l
                      LEFT JOIN item_test_set_items its
                        ON its.item_id = l.item_id
                       AND its.set_id  = (SELECT set_id FROM default_set)
                     WHERE its.id IS NULL
                ) AS ledger_rows,
                (
                    SELECT COUNT(*)
                      FROM stocks_lot s
                      LEFT JOIN item_test_set_items its
                        ON its.item_id = s.item_id
                       AND its.set_id  = (SELECT set_id FROM default_set)
                     WHERE its.id IS NULL
                ) AS stock_rows
        """
        )
        diff = (await session.execute(diff_sql)).mappings().first() or {}

        ledger_rows = int(diff.get("ledger_rows") or 0)
        stock_rows = int(diff.get("stock_rows") or 0)

        inventory_health_score = (stock_rows / ledger_rows) if ledger_rows > 0 else 1.0
        inventory_health_score = round(min(max(inventory_health_score, 0), 1), 4)

        # 2) accuracy：ledger_cut vs stocks_lot（PROD-only，按 lot_id 对齐）
        acc_ledger_sql = text(
            default_set_cte
            + """
            SELECT COUNT(*) FROM (
                SELECT
                    l.warehouse_id,
                    l.item_id,
                    l.lot_id,
                    SUM(l.delta) AS ledger_qty,
                    COALESCE(s.qty, 0) AS stock_qty
                FROM stock_ledger AS l
                LEFT JOIN item_test_set_items its
                  ON its.item_id = l.item_id
                 AND its.set_id  = (SELECT set_id FROM default_set)
                LEFT JOIN stocks_lot AS s
                  ON s.warehouse_id = l.warehouse_id
                 AND s.item_id      = l.item_id
                 AND s.lot_id       = l.lot_id
                WHERE its.id IS NULL
                GROUP BY 1,2,3, stock_qty
            ) AS x
            WHERE x.ledger_qty = x.stock_qty
        """
        )
        acc_ok = int((await session.execute(acc_ledger_sql)).scalar() or 0)

        total_slot_sql = text(
            default_set_cte
            + """
            SELECT COUNT(*)
              FROM stocks_lot s
              LEFT JOIN item_test_set_items its
                ON its.item_id = s.item_id
               AND its.set_id  = (SELECT set_id FROM default_set)
             WHERE its.id IS NULL
        """
        )
        total_slots = int((await session.execute(total_slot_sql)).scalar() or 1)
        inventory_accuracy_score = round(acc_ok / total_slots, 4)

        # 3) snapshot_accuracy：lot-only（PROD-only）
        snap_sql = text(
            default_set_cte
            + """
            SELECT COUNT(*) FROM (
                SELECT
                    l.warehouse_id,
                    l.item_id,
                    l.lot_id,
                    SUM(l.delta) AS ledger_qty,
                    COALESCE(sn.qty, 0) AS snap_qty
                FROM stock_ledger AS l
                LEFT JOIN item_test_set_items its
                  ON its.item_id = l.item_id
                 AND its.set_id  = (SELECT set_id FROM default_set)
                LEFT JOIN stock_snapshots AS sn
                  ON sn.warehouse_id   = l.warehouse_id
                 AND sn.item_id        = l.item_id
                 AND sn.lot_id         = l.lot_id
                 AND sn.snapshot_date  = CURRENT_DATE
                WHERE its.id IS NULL
                GROUP BY 1,2,3, snap_qty
            ) AS x
            WHERE x.ledger_qty = x.snap_qty
        """
        )
        snap_ok = int((await session.execute(snap_sql)).scalar() or 0)

        snapshot_row_sql = text(
            default_set_cte
            + """
            SELECT COUNT(*)
              FROM stock_snapshots sn
              LEFT JOIN item_test_set_items its
                ON its.item_id = sn.item_id
               AND its.set_id  = (SELECT set_id FROM default_set)
             WHERE sn.snapshot_date = CURRENT_DATE
               AND its.id IS NULL
        """
        )
        snap_rows = int((await session.execute(snapshot_row_sql)).scalar() or 1)
        snapshot_accuracy_score = round(snap_ok / snap_rows, 4)

        # 4) 活跃度：最近 30 天事件数量（PROD-only）
        active_sql = text(
            default_set_cte
            + """
            SELECT COUNT(*) AS active_events_30d
            FROM stock_ledger l
            LEFT JOIN item_test_set_items its
              ON its.item_id = l.item_id
             AND its.set_id  = (SELECT set_id FROM default_set)
            WHERE l.occurred_at >= NOW() - INTERVAL '30 days'
              AND its.id IS NULL
        """
        )
        active_events_30d = int((await session.execute(active_sql)).scalar() or 0)

        # 5) 过期风险：从 lots.expiry_date 读取 canonical 到期日期（只统计仍有库存 lot）
        ageing_sql = text(
            default_set_cte
            + """
            SELECT DISTINCT l.expiry_date
            FROM stocks_lot s
            JOIN lots l
              ON l.id = s.lot_id
            LEFT JOIN item_test_set_items its
              ON its.item_id = s.item_id
             AND its.set_id  = (SELECT set_id FROM default_set)
            WHERE s.qty > 0
              AND l.expiry_date IS NOT NULL
              AND its.id IS NULL
        """
        )
        rows = (await session.execute(ageing_sql)).mappings().all()

        today = datetime.now().date()
        risk_score = 0
        total_lots = 0

        for r in rows:
            exp = r.get("expiry_date")
            if exp:
                total_lots += 1
                days_left = (exp - today).days
                if days_left <= 7:
                    risk_score += 3
                elif days_left <= 14:
                    risk_score += 2
                elif days_left <= 30:
                    risk_score += 1

        expiry_risk_score = round((risk_score / (total_lots * 3)) if total_lots > 0 else 0, 4)

        # 6) 仓库效率（出库事件占比）（PROD-only）
        wh_sql = text(
            default_set_cte
            + """
            SELECT
                SUM(CASE WHEN l.delta < 0 THEN 1 ELSE 0 END) AS outbound_events,
                COUNT(*) AS total_events
            FROM stock_ledger l
            LEFT JOIN item_test_set_items its
              ON its.item_id = l.item_id
             AND its.set_id  = (SELECT set_id FROM default_set)
            WHERE its.id IS NULL
        """
        )
        wh = (await session.execute(wh_sql)).mappings().first() or {}
        warehouse_efficiency = round((wh.get("outbound_events") or 0) / (wh.get("total_events") or 1), 4)

        # 输出 key 维持历史命名，避免前端立刻炸；但 expiry 口径已切为 lot canonical
        return {
            "inventory_health_score": inventory_health_score,
            "inventory_accuracy_score": inventory_accuracy_score,
            "snapshot_accuracy_score": snapshot_accuracy_score,
            "batch_activity_30days": active_events_30d,
            "batch_risk_score": expiry_risk_score,
            "warehouse_efficiency": warehouse_efficiency,
        }
