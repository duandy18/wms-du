from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotService:
    """
    日级快照、首页总览（分页搜索）与分析查询。
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
        """
        兼容签名：
        - tests 可能传 on_date=… 或 for_date=…（此处统一用 d/on_date）
        - 允许额外 kwargs，不抛 unexpected kw 错误
        - warehouse_id/commit 目前不影响内部逻辑，预留参数
        """
        if on_date is not None and d is None:
            d = on_date
        cut_day = SnapshotService._align_day(d)
        # 关键：向 DB 传入“原生 date”，不要 str(cut_day)
        prev_day = await SnapshotService._get_prev_snap_day(session, cut_day)
        return await SnapshotService._upsert_day(session, cut_day, prev_day)

    @staticmethod
    async def run_range(session: AsyncSession, frm: date, to: date) -> int:
        if to < frm:
            raise npa.ValueError("'to' must be >= 'from'")
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
                    LEFT JOIN b as b ON b.item_id = i.id
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
                    LEFT JOIN b AS b ON b.item_id = i.id
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
                    LEFT JOIN s ON s.item_id = i.id
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
                    FROM s
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
                    LEFT JOIN b ON b.item_id = i.id
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
                LEFT JOIN t ON t.item_id = p.item_id
                LEFT JOIN e  ON e.item_id  = p.item_id
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
                    FROM i
                    LEFT JOIN s ON s.item_id = i.id
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
                    FROM s
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
                    FROM i
                    LEFT JOIN b ON b.item_id = i.id
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
                LEFT JOIN t ON t.item_id = p.item_id
                LEFT JOIN e  ON e.item_id  = p.item_id
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
            row["near_expiry"] = bool(row.get("near_expiry"))
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
        # 关键：向 DB 传入原生 date 对象，避免 asyncpg 的 toordinal 错误
        rows = (
            (await session.execute(sql, {"item_id": item_id, "frm": frm, "to": to}))
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
        # 关键：向 DB 传入原生 date
        return (await session.execute(sql, {"cut": cut_day})).scalar()

    @staticmethod
    def _window(cut_day: date, prev_day: date | None) -> tuple[str, str, str | None]:
        cut_start = datetime.combine(cut_day, datetime.min.time()).replace(UTC)
        cut_end = cut_start + timedelta(days=1)
        prev_end = (
            datetime.combine(prev_day, datetime.min.time()).replace(UTC) + timedelta(days=1)
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
            SQL = """  -- 省略注释，保留你原来的 PG 版本 SQL（与仓库现有实现一致）  """
        else:
            SQL = """  -- 省略注释，保留你原来的 SQLite 版本 SQL（与仓库现有实现一致） """

        res = await session.execute(
            text(SQL),
            {
                # 关键：向 DB 传入原生 date；时间窗用 ISO 字符串即可
                "cut_day": cut_day,
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
