# app/jobs/snapshot.py
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import async_engine

# —— 幂等覆盖：第一步删除当日 —— #
SNAP_DELETE_SQL = text(
    """
DELETE FROM stock_snapshots
WHERE snapshot_date = :cut_date;
"""
)

# —— 仅计算“当日增量”的公共 CTE（含 warehouse_id）—— #
# window_prev_end: 有前序切片 -> 取用户传入 prev_end；无前序切片 -> 取 cut_start（只算当日窗口）
DELTA_CTE = """
WITH params AS (
  SELECT
    CAST(:cut_date AS date)          AS cut_date,
    CAST(:cut_start AS timestamptz)  AS cut_start,
    CAST(:cut_end   AS timestamptz)  AS cut_end,
    CAST(:window_prev_end AS timestamptz) AS window_prev_end
),
delta AS (
  SELECT
    loc.warehouse_id,
    s.location_id,
    s.item_id,
    COALESCE(SUM(l.delta), 0) AS qty
  FROM stock_ledger l
  JOIN stocks     s   ON s.id  = l.stock_id
  JOIN locations  loc ON loc.id = s.location_id
  , params p
  WHERE l.occurred_at >  p.window_prev_end
    AND l.occurred_at <= p.cut_end
  GROUP BY loc.warehouse_id, s.location_id, s.item_id
)
"""

# —— 四种插入模板（自适应数量列 & 是否需要 warehouse_id） —— #
SNAP_INSERT_QTY_WITH_WH = text(
    DELTA_CTE
    + """
INSERT INTO stock_snapshots (snapshot_date, warehouse_id, location_id, item_id, qty)
SELECT p.cut_date, d.warehouse_id, d.location_id, d.item_id, d.qty
FROM delta d, params p;
"""
)
SNAP_INSERT_QTY_NO_WH = text(
    DELTA_CTE
    + """
INSERT INTO stock_snapshots (snapshot_date, location_id, item_id, qty)
SELECT p.cut_date, d.location_id, d.item_id, d.qty
FROM delta d, params p;
"""
)
SNAP_INSERT_QOH_WITH_WH = text(
    DELTA_CTE
    + """
INSERT INTO stock_snapshots (snapshot_date, warehouse_id, location_id, item_id, qty_on_hand, qty_available)
SELECT p.cut_date, d.warehouse_id, d.location_id, d.item_id, d.qty::integer, d.qty::integer
FROM delta d, params p;
"""
)
SNAP_INSERT_QOH_NO_WH = text(
    DELTA_CTE
    + """
INSERT INTO stock_snapshots (snapshot_date, location_id, item_id, qty_on_hand, qty_available)
SELECT p.cut_date, d.location_id, d.item_id, d.qty::integer, d.qty::integer
FROM delta d, params p;
"""
)


def _align_day(d: datetime | None) -> datetime:
    d = d or datetime.now(UTC)
    return d.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)


async def _get_snapshot_columns(engine: AsyncEngine) -> set[str]:
    sql = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'stock_snapshots'
    """
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(sql)).scalars().all()
    return {r for r in rows}


async def run_once(
    engine: AsyncEngine, *, grain: str, at: datetime | None, prev: datetime | None
) -> int:
    if grain != "day":
        raise ValueError("Only 'day' grain is supported by this job.")
    cut = _align_day(at)
    cut_start = cut
    cut_end = cut + timedelta(days=1)

    # 没有前序切片时：只算当天窗口 => window_prev_end = cut_start
    window_prev_end = (_align_day(prev) + timedelta(days=1)) if prev else cut_start

    cols = await _get_snapshot_columns(engine)
    has_wh = "warehouse_id" in cols
    use_qty = "qty" in cols
    insert_sql = (
        SNAP_INSERT_QTY_WITH_WH
        if (use_qty and has_wh)
        else (
            SNAP_INSERT_QTY_NO_WH
            if (use_qty and not has_wh)
            else SNAP_INSERT_QOH_WITH_WH if (not use_qty and has_wh) else SNAP_INSERT_QOH_NO_WH
        )
    )

    async with engine.begin() as conn:
        # 1) 幂等覆盖删除
        await conn.execute(SNAP_DELETE_SQL, {"cut_date": cut.date()})
        # 2) 插入（仅当日增量）
        await conn.execute(
            insert_sql,
            {
                "cut_date": cut.date(),
                "cut_start": cut_start,
                "cut_end": cut_end,
                "window_prev_end": window_prev_end,
            },
        )
    return 1


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def main():
    ap = argparse.ArgumentParser(description="StockSnapshot daily delta job")
    ap.add_argument("--grain", choices=["day"], default="day")
    ap.add_argument("--at", help="cut time (ISO8601); default now() aligned to 00:00Z")
    ap.add_argument(
        "--prev",
        help="override previous cut end (ISO8601); default None (uses cut_start)",
    )
    args = ap.parse_args()

    at = _parse_dt(args.at)
    prev = _parse_dt(args.prev)

    import asyncio

    asyncio.run(run_once(async_engine, grain=args.grain, at=at, prev=prev))


if __name__ == "__main__":
    main()
