# app/services/snapshot_v3_service.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotV3Service:
    """
    Snapshot v3：台账驱动快照引擎。

    能力：
      - snapshot_cut(at): 基于 stock_ledger 在指定时间点做临时切片
      - rebuild_snapshot_from_ledger(snapshot_date): 按 ledger 重算某日 stock_snapshots
      - compare_snapshot(snapshot_date): 比较 stocks / ledger_cut / snapshot 三本账的一致性
    """

    # ------------------------------------------------------------------
    # 1) 临时切片：基于 ledger 在时间点 at 生成 snapshot_cut_result 表
    # ------------------------------------------------------------------
    @staticmethod
    async def snapshot_cut(
        session: AsyncSession,
        *,
        at: datetime,
    ) -> Dict[str, Any]:
        """
        在时间点 at 做台账切片：

          snapshot_cut(at) = SUM(delta WHERE occurred_at <= at)

        结果写入临时表 snapshot_cut_result：

          (warehouse_id, item_id, batch_code, qty)

        注意：
          - 使用 TEMP TABLE，仅对当前连接可见；
          - tests / 调试工具可以基于 snapshot_cut_result 做进一步分析。
        """

        # 清空 temp 表（如果存在）
        await session.execute(text("DROP TABLE IF EXISTS snapshot_cut_result"))

        # 生成新的 temp 表
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

        # 汇总结果
        summary = (
            (
                await session.execute(
                    text(
                        """
                    SELECT
                      COUNT(*) AS slots,
                      COALESCE(SUM(qty), 0) AS total_qty
                    FROM snapshot_cut_result
                    """
                    )
                )
            )
            .mappings()
            .first()
        )

        return {
            "slot_count": int(summary["slots"]),
            "total_qty": int(summary["total_qty"]),
        }

    # ------------------------------------------------------------------
    # 2) 正式落库：用 ledger 重算某日 stock_snapshots
    # ------------------------------------------------------------------
    @staticmethod
    async def rebuild_snapshot_from_ledger(
        session: AsyncSession,
        *,
        snapshot_date: datetime,
    ) -> Dict[str, Any]:
        """
        用 ledger 重算 stock_snapshots 表（适合每天跑一次的正式快照）。

        语义：
          - snapshot_date 作为快照日期（按自然日）；
          - ledger 侧 cut 点为该日结束（[min, next_day)）；
          - 写入粒度： (snapshot_date, warehouse_id, item_id, batch_code)
          - qty_on_hand / qty_available = SUM(delta)，qty_allocated = 0
        """
        d: date = snapshot_date.date()

        # 计算 ledger 截止时间：cut_to = 当日 00:00 UTC + 1 天
        # 这里直接在 Python 层算好 timestamptz，SQL 只做 occurred_at < :cut_to，
        # 避免在 SQL 里搞 date + interval 这种类型坑。
        cut_to = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)

        # 删除同日旧快照
        await session.execute(
            text("DELETE FROM stock_snapshots WHERE snapshot_date = :d"),
            {"d": d},
        )

        # 用 ledger 重算快照
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

        # 汇总当日快照
        summary = (
            (
                await session.execute(
                    text(
                        """
                    SELECT
                      COUNT(*) AS slots,
                      COALESCE(SUM(qty_on_hand), 0) AS total_qty
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

        return {
            "snapshot_date": str(d),
            "slot_count": int(summary["slots"]),
            "total_qty": int(summary["total_qty"]),
        }

    # ------------------------------------------------------------------
    # 3) 三本账对账：ledger_cut vs snapshot vs stocks
    # ------------------------------------------------------------------
    @staticmethod
    async def compare_snapshot(
        session: AsyncSession,
        *,
        snapshot_date: datetime,
    ) -> Dict[str, Any]:
        """
        三账对账：

          1) ledger_cut: SUM(delta WHERE occurred_at <= cut_ts)
          2) snapshot : stock_snapshots WHERE snapshot_date = date(cut_ts)
          3) stocks   : 当前实时库存 stocks

        返回每个槽位的对账结果：
          {
            warehouse_id,
            item_id,
            batch_code,
            ledger_qty,
            snapshot_qty,
            stock_qty,
            diff_snapshot = ledger_qty - snapshot_qty,
            diff_stock    = ledger_qty - stock_qty
          }
        """
        cut_ts: datetime = snapshot_date
        d: date = snapshot_date.date()

        sql = """
        SELECT
            x.warehouse_id,
            x.item_id,
            x.batch_code,
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
                SUM(delta) AS ledger_qty
            FROM stock_ledger
            WHERE occurred_at <= :cut
            GROUP BY warehouse_id, item_id, batch_code
        ) AS x
        LEFT JOIN stock_snapshots s
            ON s.snapshot_date = :date
           AND s.warehouse_id = x.warehouse_id
           AND s.item_id      = x.item_id
           AND s.batch_code   = x.batch_code
        LEFT JOIN stocks st
            ON st.warehouse_id = x.warehouse_id
           AND st.item_id      = x.item_id
           AND st.batch_code   = x.batch_code;
        """

        rows = (
            (
                await session.execute(
                    text(sql),
                    {
                        "cut": cut_ts,
                        "date": d,
                    },
                )
            )
            .mappings()
            .all()
        )

        return {
            "rows": [dict(r) for r in rows],
        }
