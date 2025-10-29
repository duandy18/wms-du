# app/services/snapshot_service.py
from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SnapshotService:
    """
    日粒度快照：
      - 基于 stocks 汇总（warehouse_id + location_id + item_id）
      - UPSERT 到 stock_snapshots（UQ: snapshot_date, warehouse_id, location_id, item_id）
      - qty_available 暂等于 qty_on_hand（v1.0）
    """

    @staticmethod
    async def run_for_date(
        session: AsyncSession,
        day: date,
        *,
        sync_unbatched_from_stocks: bool = False,   # 兼容旧签名
    ) -> int:
        prev = day - timedelta(days=1)
        return await SnapshotService._upsert_day(session, day, prev)

    @staticmethod
    async def _upsert_day(session: AsyncSession, cut_day: date, prev_day: date) -> int:
        """
        以 stocks 为源，汇总 qty → stock_snapshots：
          INSERT ... SELECT
            :d               AS snapshot_date,
            l.warehouse_id   AS warehouse_id,
            s.location_id    AS location_id,
            s.item_id        AS item_id,
            CAST(SUM(s.qty) AS INT) AS qty_on_hand / qty_available
          FROM stocks s
          JOIN locations l ON l.id = s.location_id
          GROUP BY l.warehouse_id, s.location_id, s.item_id
          ON CONFLICT (snapshot_date, warehouse_id, location_id, item_id)
          DO UPDATE SET qty_on_hand=EXCLUDED.qty_on_hand,
                        qty_available=EXCLUDED.qty_available,
                        updated_at=NOW() AT TIME ZONE 'UTC'
        """
        sql = text(
            """
            INSERT INTO stock_snapshots (
                snapshot_date, warehouse_id, location_id, item_id,
                qty_on_hand,   qty_available, created_at,          updated_at
            )
            SELECT
                :d                                    AS snapshot_date,
                l.warehouse_id                        AS warehouse_id,
                s.location_id                         AS location_id,
                s.item_id                             AS item_id,
                CAST(SUM(s.qty) AS INT)               AS qty_on_hand,
                CAST(SUM(s.qty) AS INT)               AS qty_available,
                NOW() AT TIME ZONE 'UTC'              AS created_at,
                NOW() AT TIME ZONE 'UTC'              AS updated_at
            FROM stocks s
            JOIN locations l ON l.id = s.location_id
            GROUP BY l.warehouse_id, s.location_id, s.item_id
            ON CONFLICT (snapshot_date, warehouse_id, location_id, item_id)
            DO UPDATE SET
                qty_on_hand   = EXCLUDED.qty_on_hand,
                qty_available = EXCLUDED.qty_available,
                updated_at    = NOW() AT TIME ZONE 'UTC'
            """
        )

        # 直接把 cut_day（Python 的 date）作为绑定参数传入
        res = await session.execute(sql, {"d": cut_day})
        await session.commit()
        # INSERT..SELECT 的 rowcount 在 PG/SQLAlchemy 组合上可能为 -1；这里不强断言
        return res.rowcount if isinstance(res.rowcount, int) and res.rowcount >= 0 else 0
