# app/jobs/snapshot.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# 仅支持 day 粒度；后续如果要扩展 hour/week，可以在这里扩展。
VALID_GRAINS = {"day"}

VALID_SCOPES = {"PROD", "DRILL"}


SNAP_DELETE_SQL = text(
    """
    DELETE FROM public.stock_snapshots
    WHERE scope = :scope
      AND snapshot_date = :cut_date;
"""
)

SNAP_INSERT_SQL = text(
    """
    INSERT INTO public.stock_snapshots (
        scope,
        snapshot_date,
        warehouse_id,
        item_id,
        batch_code,
        qty,
        qty_allocated,
        qty_available
    )
    SELECT
        :scope AS scope,
        :cut_date AS snapshot_date,
        l.warehouse_id,
        l.item_id,
        l.batch_code,
        SUM(l.delta)      AS qty,
        0::numeric(18,4)  AS qty_allocated,
        0::numeric(18,4)  AS qty_available
    FROM stock_ledger AS l
    WHERE l.scope = :scope
      AND DATE(l.occurred_at) = :cut_date
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
    *,
    scope: str = "PROD",
) -> dict[str, Any]:
    """
    执行一次 snapshot job（当前仅支持 day 粒度）。

    ✅ 第一阶段：scope（PROD/DRILL）账本隔离
    - 默认跑 PROD 快照，避免影响运营报表口径
    - 如需 DRILL 快照，显式传 scope='DRILL'

    语义：
      - grain="day" 时：
        * cut_date = at.date()
        * 窗口为“发生日期等于 cut_date 的所有 stock_ledger.delta（按 scope 过滤）”
        * 删除该日已有的 stock_snapshots 行（按 scope 覆盖）
        * 按 (warehouse_id,item_id,batch_code) 汇总当日 stock_ledger.delta，
          将结果写入 public.stock_snapshots.qty（Stage C.2 新事实列）

      - 幂等性：同日覆盖，不累加
    """
    _ = prev
    if grain not in VALID_GRAINS:
        raise ValueError(f"Unsupported grain={grain!r}; only 'day' is implemented")

    sc = (scope or "").strip().upper()
    if sc not in VALID_SCOPES:
        raise ValueError("scope must be PROD|DRILL")

    cut_date = at.date()

    async with engine.begin() as conn:
        await conn.execute(SNAP_DELETE_SQL, {"scope": sc, "cut_date": cut_date})
        # ✅ batch_code_key 是 generated column，INSERT 不写它
        await conn.execute(SNAP_INSERT_SQL, {"scope": sc, "cut_date": cut_date})

    return {"grain": grain, "cut_date": str(cut_date), "scope": sc}
