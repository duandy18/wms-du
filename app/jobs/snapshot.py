# app/jobs/snapshot.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

# Phase 3 (lot-only): snapshot grain = (snapshot_date, warehouse_id, item_id, lot_id)
# 语义：cut_date 当天结束时刻（UTC）的库存余额（ledger 累加到 cut_to）
SNAP_INSERT_SQL = text(
    """
    INSERT INTO public.stock_snapshots (
        snapshot_date,
        warehouse_id,
        item_id,
        lot_id,
        qty,
        qty_allocated,
        qty_available
    )
    SELECT
        :cut_date AS snapshot_date,
        l.warehouse_id,
        l.item_id,
        l.lot_id,
        SUM(l.delta)      AS qty,
        0::numeric(18,4)  AS qty_allocated,
        SUM(l.delta)      AS qty_available
    FROM stock_ledger AS l
    WHERE l.occurred_at < :cut_to
    GROUP BY
        l.warehouse_id,
        l.item_id,
        l.lot_id
    HAVING SUM(l.delta) != 0
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

    Phase 3 终态（lot-only）语义：
      - grain="day" 时：
        * cut_date = at.date()
        * cut_to   = cut_date + 1 day (UTC 00:00)
        * 删除该日已有的 stock_snapshots 行
        * 按 (warehouse_id,item_id,lot_id) 汇总 occurred_at < cut_to 的 stock_ledger.delta
          将结果写入 public.stock_snapshots.qty（on-hand 快照）

      - 幂等性：同日覆盖，不累加
    """
    _ = prev
    if grain not in VALID_GRAINS:
        raise ValueError(f"Unsupported grain={grain!r}; only 'day' is implemented")

    cut_date = at.date()
    cut_to = datetime(cut_date.year, cut_date.month, cut_date.day, tzinfo=timezone.utc) + timedelta(days=1)

    async with engine.begin() as conn:
        await conn.execute(SNAP_DELETE_SQL, {"cut_date": cut_date})
        await conn.execute(SNAP_INSERT_SQL, {"cut_date": cut_date, "cut_to": cut_to})

    return {"grain": grain, "cut_date": str(cut_date)}
