from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotService:
    """
    日级快照、首页总览（分页搜索）与分析查询。
    """

    # -------------------------- Public API --------------------------

    @staticmethod
    async def run_for_date(session: AsyncSession, d: date | datetime | None) -> int:
        cut_day = SnapshotService._align_day(d)
        prev_day = await SnapshotService._get_prev_snap_day(session, cut_day)
        return await SnapshotService._upsert_day(session, cut_day, prev_day)

    @staticmethod
    async def run_range(session: AsyncSession, frm: date, to: date) -> int:
        if to < frm:
            raise ValueError("'to' must be >= 'from'")
        cur, total = frm, 0
        while cur <= to:
            prev = await SnapshotService._get_prev_snap_day(session, cur)
            total += await SnapshotService._upsert_day(session, cur, prev)
            cur = cur + timedelta(days=1)
        return total

    # === 原有首页总览（不分页）保留以兼容旧调用 ===
    @staticmethod
    async def query_inventory_snapshot(session: AsyncSession) -> list[dict]:
        near_days = int(os.getenv("WMS_NEAR_EXPIRY_DAYS", "30"))
        dialect = session.get_bind().dialect.name

        if dialect == "sqlite":
            sql = text(
                f"""
                WITH item_totals AS (
                    SELECT i.id AS item_id, i.name, '' AS spec,
                           COALESCE(SUM(s.qty), 0) AS total_qty
                    FROM items i
                    LEFT JOIN stocks s ON s.item_id = i.id
                    GROUP BY i.id, i.name
                ),
                loc_rank AS (
                    SELECT s.item_id, s.location_id, s.qty,
                           ROW_NUMBER() OVER (PARTITION BY s.item_id ORDER BY s.qty DESC, s.location_id ASC) AS rn
                    FROM stocks s
                    WHERE s.qty > 0
                ),
                top2 AS (
                    SELECT item_id,
                           json_group_array(
                               json_object('location_id', location_id, 'qty', qty)
                           ) FILTER (WHERE rn<=2) AS top2
                    FROM loc_rank
                    GROUP BY item_id
                ),
                exp AS (
                    SELECT i.id AS item_id, MIN(b.expiry_date) AS earliest_expiry
                    FROM items i
                    LEFT JOIN batches b ON b.item_id = i.id
                    GROUP BY i.id
                )
                SELECT t.item_id, t.name, t.spec, t.total_qty,
                       COALESCE(top2.top2, json('[]')) AS top2_locations,
                       e.earliest_expiry,
                       CASE
                         WHEN e.earliest_expiry IS NULL THEN 0
                         WHEN julianday(e.earliest_expiry) - julianday(date('now')) <= {near_days} THEN 1
                         ELSE 0
                       END AS near_expiry
                FROM item_totals t
                LEFT JOIN top2 ON top2.item_id = t.item_id
                LEFT JOIN exp  e ON e.item_id  = t.item_id
                ORDER BY t.item_id;
            """
            )
        else:
            sql = text(
                f"""
                WITH item_totals AS (
                    SELECT i.id AS item_id, i.name, '' AS spec,
                           COALESCE(SUM(s.qty), 0) AS total_qty
                    FROM items i
                    LEFT JOIN stocks s ON s.item_id = i.id
                    GROUP BY i.id, i.name
                ),
                loc_rank AS (
                    SELECT s.item_id, s.location_id, s.qty,
                           ROW_NUMBER() OVER (PARTITION BY s.item_id ORDER BY s.qty DESC, s.location_id ASC) AS rn
                    FROM stocks s
                    WHERE s.qty > 0
                ),
                top2 AS (
                    SELECT item_id,
                           jsonb_agg(
                               jsonb_build_object('location_id', location_id, 'qty', qty)
                               ORDER BY qty DESC, location_id ASC
                           ) FILTER (WHERE rn <= 2) AS top2
                    FROM loc_rank
                    GROUP BY item_id
                ),
                exp AS (
                    SELECT i.id AS item_id,
                           MIN(b.expiry_date) AS earliest_expiry
                    FROM items i
                    LEFT JOIN batches b ON b.item_id = i.id
                    GROUP BY i.id
                )
                SELECT t.item_id, t.name, t.spec, t.total_qty,
                       COALESCE(top2.top2, '[]'::jsonb) AS top2_locations,
                       e.earliest_expiry,
                       CASE
                         WHEN e.earliest_expiry IS NULL THEN FALSE
                         WHEN e.earliest_expiry <= (CURRENT_DATE + INTERVAL '{near_days} day')::date THEN TRUE
                         ELSE FALSE
                       END AS near_expiry
                FROM item_totals t
                LEFT JOIN top2 ON top2.item_id = t.item_id
                LEFT JOIN exp  e ON e.item_id  = t.item_id
                ORDER BY t.item_id;
            """
            )

        rows = (await session.execute(sql)).mappings().all()
        out: list[dict] = []
        for r in rows:
            item = dict(r)
            item["near_expiry"] = bool(item.get("near_expiry"))
            out.append(item)
        return out

    # === 新：首页总览分页版 /snapshot/inventory?q&offset&limit ===
    @staticmethod
    async def query_inventory_snapshot_paged(
        session: AsyncSession, q: str | None, offset: int, limit: int
    ) -> dict:
        near_days = int(os.getenv("WMS_NEAR_EXPIRY_DAYS", "30"))
        dialect = session.get_bind().dialect.name

        like = f"%{q}%" if q else None
        has_q = bool(like)

        # 1) total
        if dialect == "postgresql":
            total_sql = text(
                """
                WITH base AS (
                  SELECT i.id
                  FROM items i
                  LEFT JOIN stocks s ON s.item_id = i.id
                  WHERE (:has_q = FALSE) OR (i.name ILIKE :q OR i.sku ILIKE :q)
                  GROUP BY i.id
                )
                SELECT COUNT(*) FROM base;
                """
            )
            total = int(
                (await session.execute(total_sql, {"has_q": has_q, "q": like})).scalar() or 0
            )

            # 2) 当前页 rows
            page_sql = text(
                f"""
                WITH item_totals AS (
                    SELECT i.id AS item_id, i.name, i.sku,
                           COALESCE(SUM(s.qty), 0) AS total_qty
                    FROM items i
                    LEFT JOIN stocks s ON s.item_id = i.id
                    WHERE (:has_q = FALSE) OR (i.name ILIKE :q OR i.sku ILIKE :q)
                    GROUP BY i.id, i.name, i.sku
                ),
                it_page AS (
                    SELECT * FROM item_totals
                    ORDER BY total_qty DESC, item_id ASC
                    OFFSET :offset LIMIT :limit
                ),
                loc_rank AS (
                    SELECT s.item_id, s.location_id, s.qty,
                           ROW_NUMBER() OVER (PARTITION BY s.item_id ORDER BY s.qty DESC, s.location_id ASC) AS rn
                    FROM stocks s
                    JOIN it_page p ON p.item_id = s.item_id
                    WHERE s.qty > 0
                ),
                top2 AS (
                    SELECT item_id,
                           jsonb_agg(
                             jsonb_build_object('location_id', location_id, 'qty', qty)
                             ORDER BY qty DESC, location_id ASC
                           ) FILTER (WHERE rn <= 2) AS top2
                    FROM loc_rank
                    GROUP BY item_id
                ),
                exp AS (
                    SELECT i.id AS item_id, MIN(b.expiry_date) AS earliest_expiry
                    FROM items i
                    LEFT JOIN batches b ON b.item_id = i.id
                    JOIN it_page p ON p.item_id = i.id
                    GROUP BY i.id
                )
                SELECT p.item_id, p.name AS item_name, p.sku, p.total_qty,
                       COALESCE(t.top2, '[]'::jsonb) AS top2_locations,
                       e.earliest_expiry,
                       CASE
                         WHEN e.earliest_expiry IS NULL THEN FALSE
                         WHEN e.earliest_expiry <= (CURRENT_DATE + INTERVAL '{near_days} day')::date THEN TRUE
                         ELSE FALSE
                       END AS near_expiry
                FROM it_page p
                LEFT JOIN top2 t ON t.item_id = p.item_id
                LEFT JOIN exp  e ON e.item_id  = p.item_id
                ORDER BY p.total_qty DESC, p.item_id ASC;
                """
            )
            rows = (
                (
                    await session.execute(
                        page_sql,
                        {"has_q": has_q, "q": like, "offset": offset, "limit": limit},
                    )
                )
                .mappings()
                .all()
            )

        else:
            # SQLite 分支沿用原写法（LIKE + NULL 判定）
            total_sql = text(
                """
                WITH base AS (
                  SELECT i.id
                  FROM items i
                  LEFT JOIN stocks s ON s.item_id = i.id
                  WHERE (:q IS NULL) OR (i.name LIKE :q OR i.sku LIKE :q)
                  GROUP BY i.id
                )
                SELECT COUNT(*) FROM base;
                """
            )
            total = int((await session.execute(total_sql, {"q": like})).scalar() or 0)

            page_sql = text(
                f"""
                WITH item_totals AS (
                    SELECT i.id AS item_id, i.name, i.sku,
                           COALESCE(SUM(s.qty), 0) AS total_qty
                    FROM items i
                    LEFT JOIN stocks s ON s.item_id = i.id
                    WHERE (:q IS NULL) OR (i.name LIKE :q OR i.sku LIKE :q)
                    GROUP BY i.id, i.name, i.sku
                ),
                it_page AS (
                    SELECT * FROM item_totals
                    ORDER BY total_qty DESC, item_id ASC
                    LIMIT :limit OFFSET :offset
                ),
                loc_rank AS (
                    SELECT s.item_id, s.location_id, s.qty,
                           ROW_NUMBER() OVER (PARTITION BY s.item_id ORDER BY s.qty DESC, s.location_id ASC) AS rn
                    FROM stocks s
                    JOIN it_page p ON p.item_id = s.item_id
                    WHERE s.qty > 0
                ),
                top2 AS (
                    SELECT item_id,
                           json_group_array(
                             json_object('location_id', location_id, 'qty', qty)
                           ) FILTER (WHERE rn<=2) AS top2
                    FROM loc_rank
                    GROUP BY item_id
                ),
                exp AS (
                    SELECT i.id AS item_id, MIN(b.expiry_date) AS earliest_expiry
                    FROM items i
                    LEFT JOIN batches b ON b.item_id = i.id
                    JOIN it_page p ON p.item_id = i.id
                    GROUP BY i.id
                )
                SELECT p.item_id, p.name AS item_name, p.sku, p.total_qty,
                       COALESCE(t.top2, json('[]')) AS top2_locations,
                       e.earliest_expiry,
                       CASE
                         WHEN e.earliest_expiry IS NULL THEN 0
                         WHEN julianday(e.earliest_expiry) - julianday(date('now')) <= {near_days} THEN 1
                         ELSE 0
                       END AS near_expiry
                FROM it_page p
                LEFT JOIN top2 t ON t.item_id = p.item_id
                LEFT JOIN exp  e ON e.item_id  = p.item_id
                ORDER BY p.total_qty DESC, p.item_id ASC;
                """
            )
            rows = (
                (await session.execute(page_sql, {"q": like, "offset": offset, "limit": limit}))
                .mappings()
                .all()
            )

        out_rows: list[dict] = []
        for r in rows:
            row = dict(r)
            # PG: bool；SQLite: 0/1
            row["near_expiry"] = bool(row.get("near_expiry"))
            out_rows.append(row)

        return {"total": total, "offset": offset, "limit": limit, "rows": out_rows}

    @staticmethod
    async def trends(session: AsyncSession, item_id: int, frm: date, to: date) -> list[dict]:
        sql = text(
            """
            SELECT snapshot_date,
                   SUM(qty_on_hand)   AS qty_on_hand,
                   SUM(qty_available) AS qty_available
            FROM stock_snapshots
            WHERE item_id = :item_id
              AND snapshot_date BETWEEN :frm AND :to
            GROUP BY snapshot_date
            ORDER BY snapshot_date
            """
        )
        rows = (
            (await session.execute(sql, {"item_id": item_id, "frm": str(frm), "to": str(to)}))
            .mappings()
            .all()
        )
        return [
            {
                "snapshot_date": r["snapshot_date"],
                "qty_on_hand": int(r["qty_on_hand"]),
                "qty_available": int(r["qty_available"]),
            }
            for r in rows
        ]

    # -------------------------- Internals --------------------------

    @staticmethod
    def _align_day(d: date | datetime | None) -> date:
        if d is None:
            return datetime.now().date()
        return d.date() if isinstance(d, datetime) else d

    @staticmethod
    async def _get_prev_snap_day(session: AsyncSession, cut_day: date) -> date | None:
        sql = text("SELECT MAX(snapshot_date) FROM stock_snapshots WHERE snapshot_date < :cut")
        return (await session.execute(sql, {"cut": str(cut_day)})).scalar()

    @staticmethod
    def _window(cut_day: date, prev_day: date | None) -> tuple[str, str, str | None]:
        cut_start = datetime.combine(cut_day, datetime.min.time()).replace(tzinfo=UTC)
        cut_end = cut_start + timedelta(days=1)
        prev_end = (
            datetime.combine(prev_day, datetime.min.time()).replace(tzinfo=UTC) + timedelta(days=1)
            if prev_day is not None
            else None
        )
        return (
            cut_start.isoformat(),
            cut_end.isoformat(),
            prev_end.isoformat() if prev_end else None,
        )

    @staticmethod
    async def _upsert_day(session: AsyncSession, cut_day: date, prev_day: date | None) -> int:
        cut_start, cut_end, prev_end = SnapshotService._window(cut_day, prev_day)
        dialect = session.get_bind().dialect.name

        if dialect == "postgresql":
            SQL = """
WITH
params AS (
  SELECT :cut_day::date AS cut_day, :cut_start AS cut_start, :cut_end AS cut_end, :prev_end AS prev_end
),
base AS (
  SELECT ss.warehouse_id, ss.location_id, ss.item_id, ss.batch_id, SUM(ss.qty_on_hand) AS qty_on_hand
  FROM stock_snapshots ss, params p
  WHERE p.prev_end IS NOT NULL
    AND ss.snapshot_date = (DATE(p.prev_end) - INTERVAL '1 day')
  GROUP BY ss.warehouse_id, ss.location_id, ss.item_id, ss.batch_id
),
delta AS (
  SELECT loc.warehouse_id, s.location_id, s.item_id, l.batch_id,
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
  SELECT COALESCE(b.warehouse_id, d.warehouse_id) AS warehouse_id,
         COALESCE(b.location_id,  d.location_id)  AS location_id,
         COALESCE(b.item_id,      d.item_id)      AS item_id,
         CASE WHEN b.batch_id IS NULL AND d.batch_id IS NULL THEN NULL
              ELSE COALESCE(b.batch_id, d.batch_id) END AS batch_id,
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
  snapshot_date, warehouse_id, location_id, item_id, batch_id,
  qty_on_hand, qty_allocated, qty_available, expiry_date, age_days
)
SELECT p.cut_day, m.warehouse_id, m.location_id, m.item_id, m.batch_id,
       GREATEST(0, m.qty_on_hand)::integer AS qty_on_hand,
       0 AS qty_allocated,
       GREATEST(0, m.qty_on_hand)::integer AS qty_available,
       m.expiry_date, NULL AS age_days
FROM merged m, params p
WHERE m.qty_on_hand IS NOT NULL
ON CONFLICT (snapshot_date, warehouse_id, location_id, item_id, batch_id)
DO UPDATE SET
  qty_on_hand   = EXCLUDED.qty_on_hand,
  qty_allocated = EXCLUDED.qty_allocated,
  qty_available = EXCLUDED.qty_available,
  expiry_date   = COALESCE(EXCLUDED.expiry_date, stock_snapshots.expiry_date),
  age_days      = EXCLUDED.age_days
RETURNING 1;
            """
        else:
            SQL = """
WITH
params AS (
  SELECT :cut_day AS cut_day, :cut_start AS cut_start, :cut_end AS cut_end, :prev_end AS prev_end
),
base AS (
  SELECT ss.warehouse_id, ss.location_id, ss.item_id, ss.batch_id, SUM(ss.qty_on_hand) AS qty_on_hand
  FROM stock_snapshots ss, params p
  WHERE p.prev_end IS NOT NULL
    AND ss.snapshot_date = DATE(p.prev_end, '-1 day')
  GROUP BY ss.warehouse_id, ss.location_id, ss.item_id, ss.batch_id
),
delta AS (
  SELECT loc.warehouse_id, s.location_id, s.item_id, l.batch_id,
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
  SELECT COALESCE(b.warehouse_id, d.warehouse_id) AS warehouse_id,
         COALESCE(b.location_id,  d.location_id)  AS location_id,
         COALESCE(b.item_id,      d.item_id)      AS item_id,
         CASE WHEN b.batch_id IS NULL AND d.batch_id IS NULL THEN NULL
              ELSE COALESCE(b.batch_id, d.batch_id) END AS batch_id,
         COALESCE(b.qty_on_hand, 0) + COALESCE(d.delta_qty, 0) AS qty_on_hand,
         d.expiry_date AS expiry_date
  FROM base b
  LEFT JOIN delta d
    ON  b.warehouse_id = d.warehouse_id
    AND b.location_id  = d.location_id
    AND b.item_id      = d.item_id
    AND ( (b.batch_id IS NULL AND d.batch_id IS NULL) OR b.batch_id = d.batch_id )
  UNION ALL
  SELECT d.warehouse_id, d.location_id, d.item_id, d.batch_id, d.delta_qty, d.expiry_date
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
  snapshot_date, warehouse_id, location_id, item_id, batch_id,
  qty_on_hand, qty_allocated, qty_available, expiry_date, age_days
)
SELECT p.cut_day, m.warehouse_id, m.location_id, m.item_id, m.batch_id,
       CAST(CASE WHEN m.qty_on_hand < 0 THEN 0 ELSE m.qty_on_hand END AS INTEGER) AS qty_on_hand,
       0 AS qty_allocated,
       CAST(CASE WHEN m.qty_on_hand < 0 THEN 0 ELSE m.qty_on_hand END AS INTEGER) AS qty_available,
       m.expiry_date, NULL AS age_days
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
                "cut_day": str(cut_day),
                "cut_start": cut_start,
                "cut_end": cut_end,
                "prev_end": prev_end,
            },
        )
        await session.commit()
        try:
            rows = res.fetchall()
            return len(rows)
        except Exception:
            return int(res.rowcount or 0)
