# app/wms/snapshot/services/snapshot_run.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.snapshot.services.snapshot_time import UTC


async def _rebuild_snapshot_today_from_lot(session: AsyncSession, *, today) -> int:
    """
    Phase 4C：强一致快照生成（lot-world）

    - 永远以 stocks_lot 作为快照来源（主余额）
    - 快照 grain： (snapshot_date, warehouse_id, item_id, lot_id)
    - 删除当日快照后重建，确保与 stocks_lot 精确一致
    """
    await session.execute(
        text("DELETE FROM stock_snapshots WHERE snapshot_date = :d"),
        {"d": today},
    )
    res = await session.execute(
        text(
            """
            INSERT INTO stock_snapshots (
                snapshot_date,
                warehouse_id,
                item_id,
                lot_id,
                qty,
                qty_available,
                qty_allocated
            )
            SELECT
                :d AS snapshot_date,
                s.warehouse_id,
                s.item_id,
                s.lot_id,
                SUM(s.qty) AS qty,
                SUM(s.qty) AS qty_available,
                0 AS qty_allocated
            FROM stocks_lot AS s
            GROUP BY s.warehouse_id, s.item_id, s.lot_id
            """
        ),
        {"d": today},
    )
    return int(getattr(res, "rowcount", 0) or 0)


async def run_snapshot(session: AsyncSession) -> Dict[str, Any]:
    """
    兼容 snapshot_v2/v3 合同的入口（同事务内安全）：

    ✅ Stage C.2：以 stock_snapshots.qty 为新事实列

    Phase 4C（主写 lot-world）硬要求：
    - 三账尾门必须稳定：snapshot(today) 必须与 stocks_lot 的可观测余额一致
    - 不再信任/依赖 snapshot_today() 存储过程（其口径可能滞后或混合）
    - 因此：每次调用都强制从 stocks_lot 重建当日快照
    """
    today = datetime.now(UTC).date()

    await _rebuild_snapshot_today_from_lot(session, today=today)

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

    Phase 4E（真收口）原则：
    - 不允许任何执行路径读取 legacy stocks
    - current 余额统一以 stocks_lot 为唯一来源

    兼容字段说明：
    - sum_stocks：历史上用于“stocks 世界总量”的字段名；Phase 4E 起不再读取 stocks，
      其值与 sum_stocks_lot 相同（避免上游诊断/合同消费方 KeyError，同时确保无 legacy 表访问）
    """
    row = await session.execute(
        text(
            """
            SELECT
              COALESCE((SELECT SUM(qty) FROM stocks_lot), 0)                AS sum_stocks_lot,
              COALESCE((SELECT SUM(qty) FROM stocks_lot), 0)                AS sum_stocks,
              COALESCE((SELECT SUM(delta) FROM stock_ledger), 0)           AS sum_ledger,
              COALESCE((SELECT SUM(qty) FROM stock_snapshots), 0)          AS sum_snapshot_qty,
              COALESCE((SELECT SUM(qty_available) FROM stock_snapshots),0) AS sum_snapshot_available
            """
        )
    )
    m = row.mappings().first() or {}
    return dict(m)
