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

    ⚠️ Phase 3 要求：
    - run_snapshot 可能在“业务 commit 的同一个 session/事务”内被调用；
    - 因此这里 **绝对不能** 用 session.rollback() 回滚外层事务，
      否则会把刚写入的 stocks / stock_ledger 也一并回滚，导致“成功变失败、失败变成功”的幽灵状态。

    实现策略：
    - 对可能失败的 CALL / VIEW 读取，使用 SAVEPOINT（begin_nested）隔离失败；
    - 失败只回滚到 savepoint，不污染外层事务。
    """
    today = datetime.now(UTC).date()

    # 1) 尝试执行存储过程 snapshot_today()
    # 用 savepoint 隔离异常（例如过程不存在、权限不足等）
    called_proc = False
    try:
        async with session.begin_nested():
            await session.execute(text("CALL snapshot_today()"))
            called_proc = True
    except Exception:
        called_proc = False

    # 若未成功调用过程，则退回内建实现（同样在当前事务内执行）
    if not called_proc:
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

    # 2) 尝试读取 v_three_books 视图（隔离异常，不污染外层事务）
    summary: Optional[Dict[str, Any]] = None
    try:
        async with session.begin_nested():
            res = await session.execute(text("SELECT * FROM v_three_books"))
            m = res.mappings().first()
            if m:
                summary = dict(m)
    except Exception:
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
