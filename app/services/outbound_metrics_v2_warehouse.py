# app/services/outbound_metrics_v2_warehouse.py
from __future__ import annotations

from datetime import date
from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_outbound_v2 import (
    OutboundWarehouseMetric,
    OutboundWarehouseMetricsResponse,
)


async def load_by_warehouse(
    session: AsyncSession,
    *,
    day: date,
    platform: str,
) -> OutboundWarehouseMetricsResponse:
    sql = text(
        """
        WITH picks AS (
            SELECT
                l.warehouse_id,
                l.ref,
                sum(abs(l.delta)) AS pick_qty
            FROM stock_ledger l
            JOIN audit_events ae
              ON ae.ref = l.ref
             AND ae.category='OUTBOUND'
             AND (ae.meta->>'platform') = :platform
            WHERE l.delta < 0
              AND l.reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
              AND (l.occurred_at AT TIME ZONE 'utc')::date = :day
            GROUP BY l.warehouse_id, l.ref
        ),
        orders AS (
            SELECT
                p.warehouse_id,
                p.ref,
                bool_or(ae.meta->>'event' = 'SHIP_COMMIT') AS shipped
            FROM picks p
            JOIN audit_events ae
              ON ae.ref = p.ref
             AND ae.category='OUTBOUND'
            GROUP BY p.warehouse_id, p.ref
        )
        SELECT
            o.warehouse_id,
            count(*) AS total_orders,
            count(*) FILTER (WHERE o.shipped) AS success_orders,
            sum(p.pick_qty) AS pick_qty
        FROM orders o
        JOIN picks p
          ON p.warehouse_id = o.warehouse_id
         AND p.ref = o.ref
        GROUP BY o.warehouse_id
        ORDER BY o.warehouse_id
        """
    )
    rows = (await session.execute(sql, {"platform": platform, "day": day})).fetchall()

    wh_metrics: List[OutboundWarehouseMetric] = []
    for r in rows:
        wh_id = int(r.warehouse_id)
        total = int(r.total_orders or 0)
        success = int(r.success_orders or 0)
        pick_qty = int(r.pick_qty or 0)
        success_rate = round(success * 100.0 / total, 2) if total > 0 else 0.0
        wh_metrics.append(
            OutboundWarehouseMetric(
                warehouse_id=wh_id,
                total_orders=total,
                success_orders=success,
                success_rate=success_rate,
                pick_qty=pick_qty,
            )
        )

    return OutboundWarehouseMetricsResponse(
        day=day,
        platform=platform,
        warehouses=wh_metrics,
    )
