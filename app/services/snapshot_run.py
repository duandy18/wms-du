# app/services/snapshot_run.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_time import UTC


async def run_snapshot(session: AsyncSession) -> Dict[str, Any]:
    """
    兼容 snapshot_v2/v3 合同的入口：
    - 优先尝试调用存储过程 snapshot_today()（如存在）；
    - 尝试读取视图 v_three_books（如存在）；
    - 若上述对象不存在，则退回内建实现：
      * 以当前日期为 snapshot_date，将 stocks 汇总写入 stock_snapshots；
      * 返回一个总览字典 {sum_stocks, sum_ledger, sum_snapshot_on_hand, sum_snapshot_available}。
    """
    today = datetime.now(UTC).date()

    # 1) 尝试执行存储过程 snapshot_today()
    try:
        await session.execute(text("CALL snapshot_today()"))
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass

        await session.execute(
            text("DELETE FROM stock_snapshots WHERE snapshot_date = :d"),
            {"d": today},
        )
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
                    s.warehouse_id,
                    s.item_id,
                    s.batch_code,
                    SUM(s.qty) AS qty_on_hand,
                    SUM(s.qty) AS qty_available,
                    0 AS qty_allocated
                FROM stocks AS s
                GROUP BY s.warehouse_id, s.item_id, s.batch_code
                """
            ),
            {"d": today},
        )

    # 2) 尝试读取 v_three_books 视图
    summary: Optional[Dict[str, Any]] = None
    try:
        res = await session.execute(text("SELECT * FROM v_three_books"))
        m = res.mappings().first()
        if m:
            summary = dict(m)
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        summary = None

    # 3) 视图不存在时：手动汇总
    if summary is None:
        summary = await compute_summary(session)

    return summary


async def compute_summary(session: AsyncSession) -> Dict[str, Any]:
    """
    备用统计实现，用于在没有 v_three_books 视图时提供整体汇总。
    """
    row = await session.execute(
        text(
            """
            SELECT
              COALESCE((SELECT SUM(qty) FROM stocks), 0)                    AS sum_stocks,
              COALESCE((SELECT SUM(delta) FROM stock_ledger), 0)           AS sum_ledger,
              COALESCE((SELECT SUM(qty_on_hand) FROM stock_snapshots), 0)  AS sum_snapshot_on_hand,
              COALESCE((SELECT SUM(qty_available) FROM stock_snapshots),0) AS sum_snapshot_available
            """
        )
    )
    m = row.mappings().first() or {}
    return dict(m)
