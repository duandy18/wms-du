# app/services/snapshot_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SQL_UPSERT_SNAPSHOT_SQLITE = """
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
INSERT INTO stock_snapshots
  (snapshot_date, warehouse_id, location_id, item_id, batch_id,
   qty_on_hand, qty_allocated, qty_available, expiry_date, age_days)
SELECT
  :snap_date, warehouse_id, location_id, item_id, batch_id,
  qty_on_hand, qty_allocated, qty_available, expiry_date, age_days
FROM base
ON CONFLICT (snapshot_date, warehouse_id, location_id, item_id, batch_id)
DO UPDATE SET
  qty_on_hand   = excluded.qty_on_hand,
  qty_allocated = excluded.qty_allocated,
  qty_available = excluded.qty_available,
  expiry_date   = excluded.expiry_date,
  age_days      = excluded.age_days;
"""

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
  qty_on_hand   = excluded.qty_on_hand,
  qty_allocated = excluded.qty_allocated,
  qty_available = excluded.qty_available,
  expiry_date   = excluded.expiry_date,
  age_days      = excluded.age_days;
"""


@dataclass
class SnapshotService:
    @staticmethod
    async def run_for_date(
        session: AsyncSession,
        snap_date: date,
        *,
        sync_unbatched_from_stocks: bool = False,
    ) -> int:
        dialect = session.get_bind().dialect.name
        sql = SQL_UPSERT_SNAPSHOT_PG if dialect == "postgresql" else SQL_UPSERT_SNAPSHOT_SQLITE

        # 关键改动：直接传 Python 的 date 对象，别转字符串
        result = await session.execute(text(sql), {"snap_date": snap_date})
        await session.commit()
        return int(result.rowcount or 0)
