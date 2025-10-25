from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotService:
    """
    日级库存快照、首页总览与趋势接口。
    """

    # -------------------------- Public API --------------------------

    @staticmethod
    async def run_for_date(
        session: AsyncSession,
        d: date | datetime | None = None,
        *,
        on_date: date | datetime | None = None,
        warehouse_id: int | None = None,
        commit: bool = True,
        **_: object,
    ) -> int:
        if on_date is not None and d is None:
            d = on_date
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

    # === 原有首页总览（不分页） ===
    @staticmethod
    async def query_inventory_snapshot(session: AsyncSession) -> list[dict]:
        near_days = int(os.getenv("WMS_NEAR_EXPIRY_DAYS", "30"))
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
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
        rows = (await session.execute(sql)).mappings().all()
        out: list[dict] = []
        for r in rows:
            item = dict(r)
            item["near_expiry"] = bool(item.get("near_expiry"))
            out.append(item)
        return out

    # === 分页版 ===
    @staticmethod
    async def query_inventory_snapshot_paged(
        session: AsyncSession, q: str | None, offset: int, limit: int
    ) -> dict:
        near_days = int(os.getenv("WMS_NEAR_EXPIRY_DAYS", "30"))
        dialect = session.get_bind().dialect.name
        like = f"%{q}%" if q else None
        has_q = bool(like)

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
                ),
                merged AS (
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
                )
                SELECT * FROM merged
                ORDER BY total_qty DESC, item_id ASC;
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
                ),
                merged AS (
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
                )
                SELECT * FROM merged
                ORDER BY total_qty DESC, item_id ASC;
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
            row["near_expiry"] = bool(row.get("near_expiry"))
            out_rows.append(row)
        return {"total": total, "offset": offset, "limit": limit, "rows": out_rows}

    @staticmethod
    async def trends(session: AsyncSession, item_id: int, frm: date, to: date) -> list[dict]:
        """
        兼容两种 schema：
        A) stock_snapshots(qty_on_hand, qty_available)
        B) 较旧/极简结构只含 qty（此时 on_hand/available 都用 qty 兜底）
        """
        cols_sql = text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='stock_snapshots'
              AND column_name IN ('qty_on_hand','qty_available','qty')
            """
        )
        found = {row[0] for row in (await session.execute(cols_sql)).all()}
        qoh_col = "qty_on_hand" if "qty_on_hand" in found else ("qty" if "qty" in found else None)
        qa_col = "qty_available" if "qty_available" in found else ("qty" if "qty" in found else None)
        if qoh_col is None:
            return []

        sql = text(
            f"""
            SELECT snapshot_date,
                   SUM({qoh_col}) AS qty_on_hand,
                   SUM({qa_col or qoh_col}) AS qty_available
            FROM stock_snapshots
            WHERE item_id = :item_id
              AND snapshot_date BETWEEN :frm AND :to
            GROUP BY snapshot_date
            ORDER BY snapshot_date
            """
        )
        rows = (
            (await session.execute(sql, {"item_id": item_id, "frm": frm, "to": to}))
            .mappings()
            .all()
        )
        return [
            {
                "snapshot_date": r["snapshot_date"],
                "qty_on_hand": int(r["qty_on_hand"] or 0),
                "qty_available": int(r["qty_available"] or 0),
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
        return (await session.execute(sql, {"cut": cut_day})).scalar()

    @staticmethod
    def _window(cut_day: date, prev_day: date | None) -> tuple[str, str, str | None]:
        cut_start = datetime.combine(cut_day, datetime.min.time()).replace(tzinfo=UTC)
        cut_end = cut_start + timedelta(days=1)
        prev_end = (
            datetime.combine(prev_day, datetime.min.time()).replace(tzinfo=UTC) + timedelta(days=1)
            if prev_day is not None
            else None
        )
        return (cut_start.isoformat(), cut_end.isoformat(), prev_end.isoformat() if prev_end else None)

    @staticmethod
    async def _upsert_day(session: AsyncSession, cut_day: date, prev_day: date | None) -> int:
        """
        幂等生成 cut_day 的快照（基于 batches 聚合）。
        不依赖唯一约束；使用 CTE 先 DELETE 再 INSERT。
        """
        cols_sql = text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name='stock_snapshots'
              AND column_name IN ('qty_on_hand','qty_available','qty')
            """
        )
        found = {row[0] for row in (await session.execute(cols_sql)).all()}
        has_dual = "qty_on_hand" in found
        dialect = session.get_bind().dialect.name

        if dialect == "postgresql":
            if has_dual:
                sql = text(
                    """
                    WITH sums AS (
                      SELECT CAST(:cut_day AS date) AS snapshot_date,
                             b.item_id,
                             COALESCE(SUM(b.qty),0) AS q
                      FROM batches b
                      GROUP BY b.item_id
                    ),
                    del AS (
                      DELETE FROM stock_snapshots s
                      USING sums t
                      WHERE s.snapshot_date = t.snapshot_date AND s.item_id = t.item_id
                      RETURNING s.item_id
                    )
                    INSERT INTO stock_snapshots (snapshot_date, item_id, qty_on_hand, qty_available)
                    SELECT snapshot_date, item_id, q, q FROM sums
                    RETURNING item_id;
                    """
                )
            else:
                sql = text(
                    """
                    WITH sums AS (
                      SELECT CAST(:cut_day AS date) AS snapshot_date,
                             b.item_id,
                             COALESCE(SUM(b.qty),0) AS q
                      FROM batches b
                      GROUP BY b.item_id
                    ),
                    del AS (
                      DELETE FROM stock_snapshots s
                      USING sums t
                      WHERE s.snapshot_date = t.snapshot_date AND s.item_id = t.item_id
                      RETURNING s.item_id
                    )
                    INSERT INTO stock_snapshots (snapshot_date, item_id, qty)
                    SELECT snapshot_date, item_id, q FROM sums
                    RETURNING item_id;
                    """
                )
        else:  # SQLite
            if has_dual:
                sql = text(
                    """
                    WITH sums AS (
                      SELECT :cut_day AS snapshot_date, b.item_id, COALESCE(SUM(b.qty),0) AS q
                      FROM batches b
                      GROUP BY b.item_id
                    );
                    DELETE FROM stock_snapshots
                      WHERE (snapshot_date, item_id) IN (SELECT snapshot_date, item_id FROM sums);
                    INSERT INTO stock_snapshots (snapshot_date, item_id, qty_on_hand, qty_available)
                      SELECT snapshot_date, item_id, q, q FROM sums;
                    """
                )
            else:
                sql = text(
                    """
                    WITH sums AS (
                      SELECT :cut_day AS snapshot_date, b.item_id, COALESCE(SUM(b.qty),0) AS q
                      FROM batches b
                      GROUP BY b.item_id
                    );
                    DELETE FROM stock_snapshots
                      WHERE (snapshot_date, item_id) IN (SELECT snapshot_date, item_id FROM sums);
                    INSERT INTO stock_snapshots (snapshot_date, item_id, qty)
                      SELECT snapshot_date, item_id, q FROM sums;
                    """
                )

        res = await session.execute(sql, {"cut_day": cut_day})
        await session.commit()
        try:
            rows = res.fetchall()
            return len(rows)
        except Exception:
            return int(res.rowcount or 0)
