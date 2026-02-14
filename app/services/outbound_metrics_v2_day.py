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


# ----------------- PROD-only：测试店铺门禁（store_id 级别） -----------------
# 用于 audit_events：依赖 meta->>'platform' + meta->>'shop_id'
AUDIT_STORE_GATE = """
  AND NOT EXISTS (
    SELECT 1
      FROM stores s
      JOIN platform_test_shops pts
        ON pts.store_id = s.id
       AND pts.code = 'DEFAULT'
     WHERE upper(s.platform) = upper(audit_events.meta->>'platform')
       AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(audit_events.meta->>'shop_id' AS text))
  )
""".strip()

# 用于 stock_ledger：通过 ref 解析并 join orders，再对 orders 做 store 门禁
ORDER_STORE_GATE = """
  AND NOT EXISTS (
    SELECT 1
      FROM stores s
      JOIN platform_test_shops pts
        ON pts.store_id = s.id
       AND pts.code = 'DEFAULT'
     WHERE upper(s.platform) = upper(o.platform)
       AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(o.shop_id AS text))
  )
""".strip()


async def _calc_success_rate(
    session: AsyncSession, *, day: date, platform: str
) -> tuple[int, int, float]:
    orders_sql = text(
        f"""
        SELECT
            count(*) FILTER (WHERE (meta->>'event')='ORDER_CREATED') AS total,
            count(*) FILTER (WHERE (meta->>'event')='SHIP_COMMIT') AS success
        FROM audit_events
        WHERE category='OUTBOUND'
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
          AND (meta->>'shop_id') IS NOT NULL
          {AUDIT_STORE_GATE}
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
        f"""
        SELECT
            count(*) FILTER (WHERE meta->>'routing_event'='FALLBACK') AS fallback_times,
            count(*) FILTER (
                WHERE meta->>'routing_event' IN ('REQUEST','FALLBACK','OK')
            ) AS total_routing
        FROM audit_events
        WHERE category='ROUTING'
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
          AND (meta->>'shop_id') IS NOT NULL
          {AUDIT_STORE_GATE}
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


async def _calc_fefo_hit_rate(session: AsyncSession, *, day: date, platform: str) -> float:
    # 通过解析 ledger.ref join orders，才能拿到 shop_id 做 store 门禁
    pick_sql = text(
        f"""
        SELECT
            l.item_id,
            l.batch_code,
            l.warehouse_id,
            abs(l.delta) AS qty,
            l.occurred_at
        FROM stock_ledger l
        JOIN orders o
          ON upper(o.platform) = upper(split_part(l.ref, ':', 2))
         AND btrim(CAST(o.shop_id AS text)) = btrim(split_part(l.ref, ':', 3))
         AND btrim(CAST(o.ext_order_no AS text)) = btrim(regexp_replace(l.ref, '^ORD:[^:]+:[^:]+:', ''))
        WHERE l.delta < 0
          AND l.ref LIKE 'ORD:%'
          AND o.platform = :platform
          AND l.reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
          AND (l.occurred_at AT TIME ZONE 'utc')::date = :day
          {ORDER_STORE_GATE}
        """
    )
    rows = (await session.execute(pick_sql, {"day": day, "platform": platform})).fetchall()

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
        f"""
        SELECT
            to_char(date_trunc('hour', created_at AT TIME ZONE 'utc'), 'HH24') AS hour,
            count(*) FILTER (WHERE (meta->>'event')='ORDER_CREATED') AS orders
        FROM audit_events
        WHERE category='OUTBOUND'
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
          AND (meta->>'shop_id') IS NOT NULL
          {AUDIT_STORE_GATE}
        GROUP BY 1
        ORDER BY 1
        """
    )
    dist_rows = (
        await session.execute(dist_orders_sql, {"platform": platform, "day": day})
    ).fetchall()

    dist_pick_sql = text(
        f"""
        SELECT
            to_char(date_trunc('hour', l.occurred_at AT TIME ZONE 'utc'), 'HH24') AS hour,
            sum(abs(l.delta)) AS pick_qty
        FROM stock_ledger l
        JOIN orders o
          ON upper(o.platform) = upper(split_part(l.ref, ':', 2))
         AND btrim(CAST(o.shop_id AS text)) = btrim(split_part(l.ref, ':', 3))
         AND btrim(CAST(o.ext_order_no AS text)) = btrim(regexp_replace(l.ref, '^ORD:[^:]+:[^:]+:', ''))
        WHERE l.delta < 0
          AND l.ref LIKE 'ORD:%'
          AND o.platform = :platform
          AND l.reason IN ('PICK','OUTBOUND_SHIP','OUTBOUND_V2_SHIP','SHIP')
          AND (l.occurred_at AT TIME ZONE 'utc')::date = :day
          {ORDER_STORE_GATE}
        GROUP BY 1
        ORDER BY 1
        """
    )
    pick_rows = (await session.execute(dist_pick_sql, {"day": day, "platform": platform})).fetchall()
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
    fefo_hit_rate = await _calc_fefo_hit_rate(session, day=day, platform=platform)
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
