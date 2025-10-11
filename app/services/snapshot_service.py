# app/services/snapshot_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ==============================
# SQLite 路径：INSERT OR IGNORE + UPDATE（保留 id，兼容低版本 SQLite）
# ==============================
SQL_UPSERT_SNAPSHOT_SQLITE_INSERT = """
WITH base AS (
  SELECT
    b.warehouse_id,
    b.location_id,
    b.item_id,
    b.id AS batch_id,
    SUM(b.qty) AS qty_on_hand,
    0          AS qty_allocated,
    SUM(b.qty) AS qty_available,
    b.expiry_date,
    CAST(julianday(:snap_date) - julianday(b.production_date) AS INT) AS age_days
  FROM batches b
  GROUP BY b.warehouse_id, b.location_id, b.item_id, b.id, b.expiry_date, b.production_date
)
-- 1) 新键插入（老键忽略，不触碰原有 id）
INSERT OR IGNORE INTO stock_snapshots
  (snapshot_date, warehouse_id, location_id, item_id, batch_id,
   qty_on_hand, qty_allocated, qty_available, expiry_date, age_days)
SELECT
  :snap_date, warehouse_id, location_id, item_id, batch_id,
  qty_on_hand, qty_allocated, qty_available, expiry_date, age_days
FROM base;
"""

SQL_UPSERT_SNAPSHOT_SQLITE_UPDATE = """
WITH base AS (
  SELECT
    b.warehouse_id,
    b.location_id,
    b.item_id,
    b.id AS batch_id,
    SUM(b.qty) AS qty_on_hand,
    0          AS qty_allocated,
    SUM(b.qty) AS qty_available,
    b.expiry_date,
    CAST(julianday(:snap_date) - julianday(b.production_date) AS INT) AS age_days
  FROM batches b
  GROUP BY b.warehouse_id, b.location_id, b.item_id, b.id, b.expiry_date, b.production_date
)
-- 2) 老键更新（不删除、不重建记录，避免 id 为空报错）
UPDATE stock_snapshots AS s
SET
  qty_on_hand   = base.qty_on_hand,
  qty_allocated = base.qty_allocated,
  qty_available = base.qty_available,
  expiry_date   = base.expiry_date,
  age_days      = base.age_days
FROM base
WHERE
  s.snapshot_date = :snap_date
  AND s.warehouse_id = base.warehouse_id
  AND s.location_id  = base.location_id
  AND s.item_id      = base.item_id
  AND s.batch_id     = base.batch_id;
"""


# ==============================
# PostgreSQL 路径：ON CONFLICT DO UPDATE（保持你现有语义）
# ==============================
SQL_UPSERT_SNAPSHOT_PG = """
WITH base AS (
  SELECT
    b.warehouse_id,
    b.location_id,
    b.item_id,
    b.id AS batch_id,
    SUM(b.qty) AS qty_on_hand,
    0          AS qty_allocated,
    SUM(b.qty) AS qty_available,
    b.expiry_date,
    CAST((CAST(:snap_date AS date) - b.production_date) AS INT) AS age_days
  FROM batches b
  GROUP BY b.warehouse_id, b.location_id, b.item_id, b.id, b.expiry_date, b.production_date
)
INSERT INTO stock_snapshots
  (snapshot_date, warehouse_id, location_id, item_id, batch_id,
   qty_on_hand, qty_allocated, qty_available, expiry_date, age_days)
SELECT
  :snap_date, warehouse_id, location_id, item_id, batch_id,
  qty_on_hand, qty_allocated, qty_available, expiry_date, age_days
FROM base
ON CONFLICT (snapshot_date, warehouse_id, location_id, item_id, batch_id)
DO UPDATE SET
  qty_on_hand   = EXCLUDED.qty_on_hand,
  qty_allocated = EXCLUDED.qty_allocated,
  qty_available = EXCLUDED.qty_available,
  expiry_date   = EXCLUDED.expiry_date,
  age_days      = EXCLUDED.age_days;
"""


@dataclass
class SnapshotService:
    @staticmethod
    async def run_for_date(
        session: AsyncSession,
        snap_date: date,
        *,
        sync_unbatched_from_stocks: bool = False,  # 预留，将来需要时可启用
    ) -> int:
        """
        根据后端分流执行快照 UPSERT：
        - PostgreSQL：ON CONFLICT DO UPDATE（一次语句即可）
        - SQLite   ：INSERT OR IGNORE + UPDATE（两步，避免 REPLACE 触发 id 为空/重建）
        返回影响的行数（近似值，SQLite 为两步语句 rowcount 之和）。
        """
        dialect = session.get_bind().dialect.name  # "postgresql" / "sqlite" / ...

        if dialect == "postgresql":
            res = await session.execute(text(SQL_UPSERT_SNAPSHOT_PG), {"snap_date": snap_date})
            await session.commit()
            return int(res.rowcount or 0)

        # SQLite：两步法避免 NOT NULL id 约束失败
        res1 = await session.execute(text(SQL_UPSERT_SNAPSHOT_SQLITE_INSERT), {"snap_date": snap_date})
        res2 = await session.execute(text(SQL_UPSERT_SNAPSHOT_SQLITE_UPDATE), {"snap_date": snap_date})
        await session.commit()
        # rowcount 在不同驱动可能为 -1（未知），取非负
        n1 = max(res1.rowcount or 0, 0)
        n2 = max(res2.rowcount or 0, 0)
        return int(n1 + n2)
