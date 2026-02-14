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

    ✅ 主线 B：所有对账 join 维度统一切 batch_code_key，彻底消灭 NULL= NULL 吞数据问题。
    ✅ Stage C.2-1：snapshot 新事实列为 stock_snapshots.qty（本服务开始读 qty，不再读 qty_on_hand）。

    ✅ 运维口径（封板）：
    - 本服务为运维/诊断用途，默认只统计 PROD（排除 DEFAULT Test Set 商品），不做双口径统计。
    - 测试数据只会制造噪音，影响运维结论。
    """

    @staticmethod
    async def insights(session: AsyncSession) -> Dict[str, Any]:
        # -------------------------------------------------------------------
        # 统一：DEFAULT Test Set 过滤（PROD-only）
        # - 命中 item_test_set_items(set_id=DEFAULT,id) 的 item_id 视为 TEST
        # - 运维指标默认排除 TEST：its.id IS NULL
        # 说明：若 DEFAULT 不存在（不该发生），join 条件将无法命中，等价于“不过滤”。
        # -------------------------------------------------------------------
        default_set_cte = """
        WITH default_set AS (
            SELECT id AS set_id
              FROM item_test_sets
             WHERE code = 'DEFAULT'
             LIMIT 1
        )
        """

        # -------------------------------------------------------------------
        # 1) ledger_rows + stocks_rows — 全局结构健康（PROD-only）
        # -------------------------------------------------------------------
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
                      FROM stocks s
                      LEFT JOIN item_test_set_items its
                        ON its.item_id = s.item_id
                       AND its.set_id  = (SELECT set_id FROM default_set)
                     WHERE its.id IS NULL
                ) AS stock_rows
        """
        )
        diff = (await session.execute(diff_sql)).mappings().first()

        ledger_rows = int((diff or {}).get("ledger_rows") or 0)
        stock_rows = int((diff or {}).get("stock_rows") or 0)

        # 健康得分：库存槽位数量 / 台账事件数量（偏低表示事件过多或库存结构异常）
        inventory_health_score = (stock_rows / ledger_rows) if ledger_rows > 0 else 1.0
        inventory_health_score = round(min(max(inventory_health_score, 0), 1), 4)

        # -------------------------------------------------------------------
        # 2) accuracy：ledger_cut vs stocks（PROD-only）
        # -------------------------------------------------------------------
        acc_ledger_sql = text(
            default_set_cte
            + """
            SELECT COUNT(*) FROM (
                SELECT
                    l.warehouse_id, l.item_id, l.batch_code_key,
                    SUM(l.delta) AS ledger_qty,
                    s.qty AS stock_qty
                FROM stock_ledger AS l
                LEFT JOIN item_test_set_items its
                  ON its.item_id = l.item_id
                 AND its.set_id  = (SELECT set_id FROM default_set)
                LEFT JOIN stocks AS s
                  ON s.warehouse_id   = l.warehouse_id
                 AND s.item_id        = l.item_id
                 AND s.batch_code_key = l.batch_code_key
                WHERE its.id IS NULL
                GROUP BY 1,2,3, s.qty
            ) AS x
            WHERE x.ledger_qty = x.stock_qty
        """
        )
        acc_ok = int((await session.execute(acc_ledger_sql)).scalar() or 0)

        total_slot_sql = text(
            default_set_cte
            + """
            SELECT COUNT(*)
              FROM stocks s
              LEFT JOIN item_test_set_items its
                ON its.item_id = s.item_id
               AND its.set_id  = (SELECT set_id FROM default_set)
             WHERE its.id IS NULL
        """
        )
        total_slots = int((await session.execute(total_slot_sql)).scalar() or 1)

        inventory_accuracy_score = round(acc_ok / total_slots, 4)

        # -------------------------------------------------------------------
        # 3) snapshot_accuracy：ledger vs snapshot_v3（PROD-only）
        # -------------------------------------------------------------------
        snap_sql = text(
            default_set_cte
            + """
            SELECT COUNT(*) FROM (
                SELECT
                    l.warehouse_id, l.item_id, l.batch_code_key,
                    SUM(l.delta) AS ledger_qty,
                    COALESCE(s.qty, 0) AS snap_qty
                FROM stock_ledger AS l
                LEFT JOIN item_test_set_items its
                  ON its.item_id = l.item_id
                 AND its.set_id  = (SELECT set_id FROM default_set)
                LEFT JOIN stock_snapshots AS s
                  ON s.warehouse_id   = l.warehouse_id
                 AND s.item_id        = l.item_id
                 AND s.batch_code_key = l.batch_code_key
                 AND s.snapshot_date  = CURRENT_DATE
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

        # -------------------------------------------------------------------
        # 4) 批次活跃度：最近 30 天事件数量（PROD-only）
        # -------------------------------------------------------------------
        active_sql = text(
            default_set_cte
            + """
            SELECT COUNT(*) AS active_batches
            FROM stock_ledger l
            LEFT JOIN item_test_set_items its
              ON its.item_id = l.item_id
             AND its.set_id  = (SELECT set_id FROM default_set)
            WHERE l.occurred_at >= NOW() - INTERVAL '30 days'
              AND its.id IS NULL
        """
        )
        active_batches = int((await session.execute(active_sql)).scalar() or 0)

        # -------------------------------------------------------------------
        # 5) 批次老化风险指数 batch_risk_score（PROD-only）
        #     - <=7 天 HIGH
        #     - <=14 天 MED
        #     - <=30 天 LOW
        # -------------------------------------------------------------------
        ageing_sql = text(
            default_set_cte
            + """
            SELECT b.expiry_date
            FROM batches b
            LEFT JOIN item_test_set_items its
              ON its.item_id = b.item_id
             AND its.set_id  = (SELECT set_id FROM default_set)
            WHERE b.expiry_date IS NOT NULL
              AND its.id IS NULL
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
        # 6) 仓库效率（出库事件占比）（PROD-only）
        # -------------------------------------------------------------------
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
