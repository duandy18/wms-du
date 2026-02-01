# app/jobs/snapshot.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# 仅支持 day 粒度；后续如果要扩展 hour/week，可以在这里扩展。
VALID_GRAINS = {"day"}


SNAP_DELETE_SQL = text(
    """
    DELETE FROM public.stock_snapshots
    WHERE snapshot_date = :cut_date;
"""
)

SNAP_INSERT_SQL = text(
    """
    INSERT INTO public.stock_snapshots (
        snapshot_date,
        warehouse_id,
        item_id,
        batch_code,
        qty_on_hand,
        qty_allocated,
        qty_available
    )
    SELECT
        :cut_date AS snapshot_date,
        l.warehouse_id,
        l.item_id,
        l.batch_code,
        SUM(l.delta)      AS qty_on_hand,
        0::numeric(18,4)  AS qty_allocated,
        0::numeric(18,4)  AS qty_available
    FROM stock_ledger AS l
    WHERE DATE(l.occurred_at) = :cut_date
    GROUP BY
        l.warehouse_id,
        l.item_id,
        l.batch_code
"""
)


async def run_once(
    engine: AsyncEngine,
    grain: str,
    at: datetime,
    prev: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    执行一次 snapshot job（当前仅支持 day 粒度）。

    语义（与 tests/quick/test_stock_snapshot_pg.py / backfill_pg.py 对齐）：

      - grain="day" 时：
        * cut_date = at.date()
        * 窗口为“发生日期等于 cut_date 的所有 stock_ledger.delta”
        * 删除该日已有的 stock_snapshots 行
        * 按 (warehouse_id,item_id,batch_code) 汇总当日 stock_ledger.delta，
          将结果写入 public.stock_snapshots.qty_on_hand

      - 幂等性：
        * 对同一 cut_date 重复调用 run_once，只会覆盖同一日记录，不会累加。

      - backfill：
        * 对 T 先跑，再跑 T-1，只会影响各自日期的记录，互不污染。
    """
    if grain not in VALID_GRAINS:
        raise ValueError(f"Unsupported grain={grain!r}; only 'day' is implemented")

    cut_date = at.date()

    async with engine.begin() as conn:
        await conn.execute(SNAP_DELETE_SQL, {"cut_date": cut_date})
        # ✅ batch_code_key 是 generated column，INSERT 不写它
        await conn.execute(SNAP_INSERT_SQL, {"cut_date": cut_date})

    return {"grain": grain, "cut_date": str(cut_date)}
