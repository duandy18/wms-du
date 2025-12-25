# app/services/outbound_metrics_v2_day.py
from __future__ import annotations

from datetime import date, datetime
from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_outbound_v2 import (
    OutboundDistributionPoint,
    OutboundMetricsV2,
)


async def _calc_success_rate(
    session: AsyncSession, *, day: date, platform: str
) -> tuple[int, int, float]:
    orders_sql = text(
        """
        SELECT
            count(*) FILTER (WHERE (meta->>'event')='ORDER_CREATED') AS total,
            count(*) FILTER (WHERE (meta->>'event')='SHIP_COMMIT') AS success
        FROM audit_events
        WHERE category='OUTBOUND'
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
        """
    )
    r = await session.execute(orders_sql, {"platform": platform, "day": day})
    row = r.fetchone()
    total_orders = int(row.total or 0) if row else 0
    success_orders = int(row.success or 0) if row else 0
    if total_orders > 0:
        success_rate = round(success_orders * 100.0 / total_orders, 2)
    else:
        success_rate = 0.0
    return total_orders, success_orders, success_rate


async def _calc_fallback_rate(
    session: AsyncSession, *, day: date, platform: str
) -> tuple[int, int, float]:
    routing_sql = text(
        """
        SELECT
            count(*) FILTER (WHERE meta->>'routing_event'='FALLBACK') AS fallback_times,
            count(*) FILTER (
                WHERE meta->>'routing_event' IN ('REQUEST','FALLBACK','OK')
            ) AS total_routing
        FROM audit_events
        WHERE category='ROUTING'
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
        """
    )
    r = await session.execute(routing_sql, {"platform": platform, "day": day})
    row = r.fetchone()
    fallback_times = int((row and row.fallback_times) or 0)
    total_routing = int((row and row.total_routing) or 0)
    if total_routing > 0:
        fallback_rate = round(fallback_times * 100.0 / total_routing, 2)
    else:
        fallback_rate = 0.0
    return fallback_times, total_routing, fallback_rate


async def _calc_fefo_hit_rate(session: AsyncSession, *, day: date) -> float:
    pick_sql = text(
        """
        SELECT
            l.item_id,
            l.batch_code,
            l.warehouse_id,
            abs(l.delta) AS qty,
            l.occurred_at
        FROM stock_ledger l
        WHERE l.delta < 0
          AND l.reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
          AND (l.occurred_at AT TIME ZONE 'utc')::date = :day
        """
    )
    rows = (await session.execute(pick_sql, {"day": day})).fetchall()

    fefo_correct = 0
    fefo_total = 0

    for item_id, batch_code, wh_id, qty, occurred_at in rows:
        bsql = text(
            """
            SELECT batch_code, expiry_date
            FROM batches
            WHERE item_id = :item_id
            """
        )
        br = (await session.execute(bsql, {"item_id": item_id})).fetchall()
        if not br:
            continue

        sorted_batches = sorted(
            [(b.batch_code, b.expiry_date) for b in br],
            key=lambda x: x[1] or datetime.max.replace(tzinfo=None),
        )
        fefo_batch = sorted_batches[0][0]

        fefo_total += 1
        if batch_code == fefo_batch:
            fefo_correct += 1

    if fefo_total > 0:
        return round(fefo_correct * 100.0 / fefo_total, 2)
    return 0.0


async def _calc_distribution(
    session: AsyncSession,
    *,
    day: date,
    platform: str,
) -> List[OutboundDistributionPoint]:
    dist_orders_sql = text(
        """
        SELECT
            to_char(date_trunc('hour', created_at AT TIME ZONE 'utc'), 'HH24') AS hour,
            count(*) FILTER (WHERE (meta->>'event')='ORDER_CREATED') AS orders
        FROM audit_events
        WHERE category='OUTBOUND'
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
        GROUP BY 1
        ORDER BY 1
        """
    )
    dist_rows = (
        await session.execute(dist_orders_sql, {"platform": platform, "day": day})
    ).fetchall()

    dist_pick_sql = text(
        """
        SELECT
            to_char(date_trunc('hour', occurred_at AT TIME ZONE 'utc'), 'HH24') AS hour,
            sum(abs(delta)) AS pick_qty
        FROM stock_ledger
        WHERE delta < 0
          AND reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
          AND (occurred_at AT TIME ZONE 'utc')::date = :day
        GROUP BY 1
        ORDER BY 1
        """
    )
    pick_rows = (await session.execute(dist_pick_sql, {"day": day})).fetchall()
    picks_map = {r.hour: int(r.pick_qty or 0) for r in pick_rows}

    distribution: List[OutboundDistributionPoint] = []
    for r in dist_rows:
        distribution.append(
            OutboundDistributionPoint(
                hour=r.hour,
                orders=int(r.orders or 0),
                pick_qty=picks_map.get(r.hour, 0),
            )
        )
    return distribution


async def load_day(
    session: AsyncSession,
    *,
    day: date,
    platform: str,
) -> OutboundMetricsV2:
    total_orders, success_orders, success_rate = await _calc_success_rate(
        session,
        day=day,
        platform=platform,
    )
    fallback_times, total_routing, fallback_rate = await _calc_fallback_rate(
        session,
        day=day,
        platform=platform,
    )
    fefo_hit_rate = await _calc_fefo_hit_rate(session, day=day)
    distribution = await _calc_distribution(session, day=day, platform=platform)

    return OutboundMetricsV2(
        day=day,
        platform=platform,
        total_orders=total_orders,
        success_orders=success_orders,
        success_rate=success_rate,
        fallback_times=fallback_times,
        fallback_rate=fallback_rate,
        fefo_hit_rate=fefo_hit_rate,
        distribution=distribution,
    )
