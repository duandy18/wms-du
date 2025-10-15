# app/services/snapshot_service.py
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotService:
    """
    日级快照（幂等 + 可回灌），采用“上一日快照 + ledger 增量”的通用算法，
    同时覆盖“无批次（batch_id IS NULL）”与“有批次”的库存变动。

    关键点：
    - base：上一日 snapshot 的 qty_on_hand（按 warehouse/location/item/batch 维度）
    - delta：在 (prev_end, cut_end] 窗口内的台账增量（通过 stocks→locations 拿到 warehouse_id）
    - merged = base + delta
    - UPSERT 到 stock_snapshots（唯一键：snapshot_date, warehouse_id, location_id, item_id, batch_id）
    - expiry_date：窗口内出现的批次到期日最小值（若无批次则为 NULL）
    - qty_allocated = 0、qty_available = on_hand（后续可接“预留”表叠加）
    """

    # -------------------------- Public API --------------------------

    @staticmethod
    async def run_for_date(session: AsyncSession, d: date | datetime | None) -> int:
        """
        生成某一天的快照（幂等覆盖）。
        返回近似受影响行数（不同 DB/驱动对 rowcount/returning 的支持差异较大，值仅供参考）。
        """
        cut_day = SnapshotService._align_day(d)
        prev_day = await SnapshotService._get_prev_snap_day(session, cut_day)
        return await SnapshotService._upsert_day(session, cut_day, prev_day)

    @staticmethod
    async def run_range(session: AsyncSession, frm: date, to: date) -> int:
        """
        回灌 [frm, to]（含两端）。逐日依赖，确保 base 来自前一日快照。
        """
        if to < frm:
            raise ValueError("'to' must be >= 'from'")
        cur, total = frm, 0
        while cur <= to:
            prev = await SnapshotService._get_prev_snap_day(session, cur)
            total += await SnapshotService._upsert_day(session, cur, prev)
            cur = cur + timedelta(days=1)
        return total

    # -------------------------- Internals --------------------------

    @staticmethod
    def _align_day(d: date | datetime | None) -> date:
        if d is None:
            # 使用本地时区的“今天”；如需特定时区可自行调参
            return datetime.now().date()
        return d.date() if isinstance(d, datetime) else d

    @staticmethod
    async def _get_prev_snap_day(session: AsyncSession, cut_day: date) -> date | None:
        sql = text(
            """
            SELECT MAX(snapshot_date)::date
            FROM stock_snapshots
            WHERE snapshot_date < :cut
        """
        )
        return (await session.execute(sql, {"cut": cut_day})).scalar()

    @staticmethod
    def _window(cut_day: date, prev_day: date | None) -> tuple[str, str, str | None]:
        """
        返回 (cut_start_iso, cut_end_iso, prev_end_iso)
        以 ISO8601 字符串传参，兼容不同方言的 DATETIME 比较。
        窗口定义： (prev_end, cut_end] ；其中 prev_end = prev_day + 1day 00:00:00
        """
        cut_start = datetime.combine(cut_day, datetime.min.time()).replace(tzinfo=UTC)
        cut_end = cut_start + timedelta(days=1)
        prev_end = None
        if prev_day is not None:
            prev_end = datetime.combine(prev_day, datetime.min.time()).replace(
                tzinfo=UTC
            ) + timedelta(days=1)
        # 转成 ISO 字符串；SQLite/PG 都能按字符串比较时间戳（同一格式）
        return (
            cut_start.isoformat(),
            cut_end.isoformat(),
            prev_end.isoformat() if prev_end else None,
        )

    @staticmethod
    async def _upsert_day(session: AsyncSession, cut_day: date, prev_day: date | None) -> int:
        cut_start, cut_end, prev_end = SnapshotService._window(cut_day, prev_day)
        dialect = session.get_bind().dialect.name  # "postgresql" / "sqlite" / others

        # 说明：
        # - base：取上一日 snapshot（若 prev_day 为空则 base 为空集）
        # - delta：从 stock_ledger 聚合，加入 stocks/locations 推导 warehouse_id，LEFT JOIN batches 获得 expiry
        # - merged：FULL JOIN base 与 delta；NULL batch_id 需特判为“相等”
        # - upsert：PG 用 RETURNING 统计影响；SQLite 新版也支持 RETURNING，但兼容起见做 rowcount 回落

        SQL = f"""
WITH
params AS (
  SELECT
    :cut_day::date   AS cut_day,
    :cut_start       AS cut_start,
    :cut_end         AS cut_end,
    :prev_end        AS prev_end
),
base AS (
  SELECT
    ss.warehouse_id,
    ss.location_id,
    ss.item_id,
    ss.batch_id,
    SUM(ss.qty_on_hand) AS qty_on_hand
  FROM stock_snapshots ss, params p
  WHERE p.prev_end IS NOT NULL
    AND ss.snapshot_date = (DATE(p.prev_end) - INTERVAL '1 day')
  GROUP BY ss.warehouse_id, ss.location_id, ss.item_id, ss.batch_id
),
delta AS (
  SELECT
    loc.warehouse_id,
    s.location_id,
    s.item_id,
    l.batch_id,
    COALESCE(SUM(l.delta), 0) AS delta_qty,
    MIN(b.expiry_date) FILTER (WHERE b.expiry_date IS NOT NULL) AS expiry_date
  FROM stock_ledger l
  JOIN stocks s      ON s.id  = l.stock_id
  JOIN locations loc ON loc.id = s.location_id
  LEFT JOIN batches b ON b.id  = l.batch_id
  , params p
  WHERE (p.prev_end IS NULL OR l.occurred_at >  p.prev_end)
    AND   l.occurred_at <= p.cut_end
  GROUP BY loc.warehouse_id, s.location_id, s.item_id, l.batch_id
),
merged AS (
  SELECT
    COALESCE(b.warehouse_id, d.warehouse_id) AS warehouse_id,
    COALESCE(b.location_id,  d.location_id)  AS location_id,
    COALESCE(b.item_id,      d.item_id)      AS item_id,
    -- 批次维度的“空=空”匹配：当双方均为 NULL 视为同一批次
    CASE WHEN b.batch_id IS NULL AND d.batch_id IS NULL THEN NULL
         ELSE COALESCE(b.batch_id, d.batch_id) END    AS batch_id,
    COALESCE(b.qty_on_hand, 0) + COALESCE(d.delta_qty, 0) AS qty_on_hand,
    d.expiry_date AS expiry_date
  FROM base b
  FULL JOIN delta d
    ON  b.warehouse_id = d.warehouse_id
    AND b.location_id  = d.location_id
    AND b.item_id      = d.item_id
    AND ( (b.batch_id IS NULL AND d.batch_id IS NULL) OR b.batch_id = d.batch_id )
)
INSERT INTO stock_snapshots (
  snapshot_date,
  warehouse_id,
  location_id,
  item_id,
  batch_id,
  qty_on_hand,
  qty_allocated,
  qty_available,
  expiry_date,
  age_days
)
SELECT
  p.cut_day                               AS snapshot_date,
  m.warehouse_id,
  m.location_id,
  m.item_id,
  m.batch_id,
  GREATEST(0, m.qty_on_hand)::integer     AS qty_on_hand,
  0                                       AS qty_allocated,
  GREATEST(0, m.qty_on_hand)::integer     AS qty_available,
  m.expiry_date                           AS expiry_date,
  NULL                                    AS age_days
FROM merged m, params p
WHERE m.qty_on_hand IS NOT NULL
ON CONFLICT (snapshot_date, warehouse_id, location_id, item_id, batch_id)
DO UPDATE SET
  qty_on_hand   = EXCLUDED.qty_on_hand,
  qty_allocated = EXCLUDED.qty_allocated,
  qty_available = EXCLUDED.qty_available,
  expiry_date   = COALESCE(EXCLUDED.expiry_date, stock_snapshots.expiry_date),
  age_days      = EXCLUDED.age_days
{"RETURNING 1" if dialect == "postgresql" else ""};
        """

        # SQLite 不支持 ::date / INTERVAL 语法；做一版方言分支（等价逻辑）
        if dialect == "sqlite":
            SQL = """
WITH
params AS (
  SELECT
    :cut_day AS cut_day,
    :cut_start AS cut_start,
    :cut_end AS cut_end,
    :prev_end AS prev_end
),
base AS (
  SELECT
    ss.warehouse_id,
    ss.location_id,
    ss.item_id,
    ss.batch_id,
    SUM(ss.qty_on_hand) AS qty_on_hand
  FROM stock_snapshots ss, params p
  WHERE p.prev_end IS NOT NULL
    AND ss.snapshot_date = DATE(p.prev_end, '-1 day')
  GROUP BY ss.warehouse_id, ss.location_id, ss.item_id, ss.batch_id
),
delta AS (
  SELECT
    loc.warehouse_id,
    s.location_id,
    s.item_id,
    l.batch_id,
    COALESCE(SUM(l.delta), 0) AS delta_qty,
    MIN(b.expiry_date) AS expiry_date
  FROM stock_ledger l
  JOIN stocks s      ON s.id  = l.stock_id
  JOIN locations loc ON loc.id = s.location_id
  LEFT JOIN batches b ON b.id  = l.batch_id
  , params p
  WHERE (p.prev_end IS NULL OR l.occurred_at >  p.prev_end)
    AND   l.occurred_at <= p.cut_end
  GROUP BY loc.warehouse_id, s.location_id, s.item_id, l.batch_id
),
merged AS (
  SELECT
    COALESCE(b.warehouse_id, d.warehouse_id) AS warehouse_id,
    COALESCE(b.location_id,  d.location_id)  AS location_id,
    COALESCE(b.item_id,      d.item_id)      AS item_id,
    CASE WHEN b.batch_id IS NULL AND d.batch_id IS NULL THEN NULL
         ELSE COALESCE(b.batch_id, d.batch_id) END    AS batch_id,
    COALESCE(b.qty_on_hand, 0) + COALESCE(d.delta_qty, 0) AS qty_on_hand,
    d.expiry_date AS expiry_date
  FROM base b
  LEFT JOIN delta d
    ON  b.warehouse_id = d.warehouse_id
    AND b.location_id  = d.location_id
    AND b.item_id      = d.item_id
    AND ( (b.batch_id IS NULL AND d.batch_id IS NULL) OR b.batch_id = d.batch_id )
  UNION ALL
  SELECT
    d.warehouse_id, d.location_id, d.item_id, d.batch_id,
    d.delta_qty AS qty_on_hand, d.expiry_date
  FROM delta d
  WHERE NOT EXISTS (
    SELECT 1 FROM base b
    WHERE b.warehouse_id = d.warehouse_id
      AND b.location_id  = d.location_id
      AND b.item_id      = d.item_id
      AND ( (b.batch_id IS NULL AND d.batch_id IS NULL) OR b.batch_id = d.batch_id )
  )
)
INSERT INTO stock_snapshots (
  snapshot_date,
  warehouse_id,
  location_id,
  item_id,
  batch_id,
  qty_on_hand,
  qty_allocated,
  qty_available,
  expiry_date,
  age_days
)
SELECT
  p.cut_day                               AS snapshot_date,
  m.warehouse_id,
  m.location_id,
  m.item_id,
  m.batch_id,
  CAST(CASE WHEN m.qty_on_hand < 0 THEN 0 ELSE m.qty_on_hand END AS INTEGER) AS qty_on_hand,
  0 AS qty_allocated,
  CAST(CASE WHEN m.qty_on_hand < 0 THEN 0 ELSE m.qty_on_hand END AS INTEGER) AS qty_available,
  m.expiry_date,
  NULL AS age_days
FROM merged m, params p
WHERE m.qty_on_hand IS NOT NULL
ON CONFLICT (snapshot_date, warehouse_id, location_id, item_id, batch_id)
DO UPDATE SET
  qty_on_hand   = EXCLUDED.qty_on_hand,
  qty_allocated = EXCLUDED.qty_allocated,
  qty_available = EXCLUDED.qty_available,
  expiry_date   = COALESCE(EXCLUDED.expiry_date, stock_snapshots.expiry_date),
  age_days      = EXCLUDED.age_days;
            """

        res = await session.execute(
            text(SQL),
            {
                "cut_day": str(cut_day),  # 'YYYY-MM-DD'
                "cut_start": cut_start,
                "cut_end": cut_end,
                "prev_end": prev_end,
            },
        )
        await session.commit()

        # 结果统计：PG 走 RETURNING 的长度；SQLite 退回 rowcount（可能为 -1/None）
        try:
            rows = res.fetchall()
            return len(rows)
        except Exception:
            return int(res.rowcount or 0)
