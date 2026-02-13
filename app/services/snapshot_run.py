# app/services/snapshot_run.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_time import UTC


async def run_snapshot(session: AsyncSession) -> Dict[str, Any]:
    """
    兼容 snapshot_v2/v3 合同的入口（同事务内安全）：

    ✅ Stage C.2：以 stock_snapshots.qty 为新事实列
    """
    today = datetime.now(UTC).date()

    called_proc = False
    try:
        async with session.begin_nested():
            await session.execute(text("CALL snapshot_today()"))
            called_proc = True
    except Exception:
        called_proc = False

    if not called_proc:
        await session.execute(
            text("DELETE FROM stock_snapshots WHERE snapshot_date = :d"),
            {"d": today},
        )
        # ✅ batch_code_key 是 generated column，INSERT 不写它
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
                    s.warehouse_id,
                    s.item_id,
                    s.batch_code,
                    SUM(s.qty) AS qty,
                    SUM(s.qty) AS qty_available,
                    0 AS qty_allocated
                FROM stocks AS s
                GROUP BY s.warehouse_id, s.item_id, s.batch_code
                """
            ),
            {"d": today},
        )

    summary: Optional[Dict[str, Any]] = None
    try:
        async with session.begin_nested():
            res = await session.execute(text("SELECT * FROM v_three_books"))
            m = res.mappings().first()
            if m:
                summary = dict(m)
    except Exception:
        summary = None

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
              COALESCE((SELECT SUM(qty) FROM stock_snapshots), 0)          AS sum_snapshot_qty,
              COALESCE((SELECT SUM(qty_available) FROM stock_snapshots),0) AS sum_snapshot_available
            """
        )
    )
    m = row.mappings().first() or {}
    return dict(m)
