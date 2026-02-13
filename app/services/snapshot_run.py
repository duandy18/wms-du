# app/services/snapshot_run.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.snapshot_time import UTC


_VALID_SCOPES = {"PROD", "DRILL"}


def _norm_scope(scope: Optional[str]) -> str:
    sc = (scope or "").strip().upper() or "PROD"
    if sc not in _VALID_SCOPES:
        raise ValueError("scope must be PROD|DRILL")
    return sc


async def run_snapshot(session: AsyncSession, *, scope: str = "PROD") -> Dict[str, Any]:
    """
    兼容 snapshot_v2/v3 合同的入口（同事务内安全）：

    ✅ Stage C.2：以 stock_snapshots.qty 为新事实列

    ✅ Scope 第一阶段：
    - 默认仅跑 PROD 口径快照，避免训练口径混入运营口径
    """
    sc = _norm_scope(scope)
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
            text("DELETE FROM stock_snapshots WHERE scope = :scope AND snapshot_date = :d"),
            {"scope": sc, "d": today},
        )
        # ✅ batch_code_key 是 generated column，INSERT 不写它
        await session.execute(
            text(
                """
                INSERT INTO stock_snapshots (
                    scope,
                    snapshot_date,
                    warehouse_id,
                    item_id,
                    batch_code,
                    qty,
                    qty_available,
                    qty_allocated
                )
                SELECT
                    :scope AS scope,
                    :d AS snapshot_date,
                    s.warehouse_id,
                    s.item_id,
                    s.batch_code,
                    SUM(s.qty) AS qty,
                    SUM(s.qty) AS qty_available,
                    0 AS qty_allocated
                FROM stocks AS s
                WHERE s.scope = :scope
                GROUP BY s.warehouse_id, s.item_id, s.batch_code
                """
            ),
            {"scope": sc, "d": today},
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
        summary = await compute_summary(session, scope=sc)

    return summary


async def compute_summary(session: AsyncSession, *, scope: str = "PROD") -> Dict[str, Any]:
    """
    备用统计实现，用于在没有 v_three_books 视图时提供整体汇总。

    ✅ Scope 第一阶段：按 scope 过滤三本账汇总
    """
    sc = _norm_scope(scope)

    row = await session.execute(
        text(
            """
            SELECT
              COALESCE((SELECT SUM(qty) FROM stocks WHERE scope = :scope), 0)                    AS sum_stocks,
              COALESCE((SELECT SUM(delta) FROM stock_ledger WHERE scope = :scope), 0)           AS sum_ledger,
              COALESCE((SELECT SUM(qty) FROM stock_snapshots WHERE scope = :scope), 0)          AS sum_snapshot_qty,
              COALESCE((SELECT SUM(qty_available) FROM stock_snapshots WHERE scope = :scope),0) AS sum_snapshot_available
            """
        ),
        {"scope": sc},
    )
    m = row.mappings().first() or {}
    return dict(m)
