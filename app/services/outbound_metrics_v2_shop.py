# app/services/outbound_metrics_v2_shop.py
from __future__ import annotations

from datetime import date
from typing import Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_outbound_v2 import OutboundShopMetric, OutboundShopMetricsResponse


async def load_by_shop(
    session: AsyncSession,
    *,
    day: date,
    platform: str,
) -> OutboundShopMetricsResponse:
    sql = text(
        """
        WITH orders AS (
            SELECT
                COALESCE(meta->>'shop_id', 'UNKNOWN') AS shop_id,
                meta->>'event' AS event,
                ref
            FROM audit_events
            WHERE category='OUTBOUND'
              AND (meta->>'platform') = :platform
              AND (created_at AT TIME ZONE 'utc')::date = :day
        )
        SELECT
            shop_id,
            count(*) FILTER (WHERE event='ORDER_CREATED') AS total_orders,
            count(*) FILTER (WHERE event='SHIP_COMMIT') AS success_orders
        FROM orders
        GROUP BY shop_id
        ORDER BY shop_id
        """
    )
    rows = (await session.execute(sql, {"platform": platform, "day": day})).fetchall()

    routing_sql = text(
        """
        SELECT
            COALESCE(meta->>'shop_id', 'UNKNOWN') AS shop_id,
            count(*) FILTER (WHERE meta->>'routing_event'='FALLBACK') AS fallback_times,
            count(*) FILTER (
                WHERE meta->>'routing_event' IN ('REQUEST','FALLBACK','OK')
            ) AS total_routing
        FROM audit_events
        WHERE category='ROUTING'
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
        GROUP BY shop_id
        """
    )
    r_rows = (await session.execute(routing_sql, {"platform": platform, "day": day})).fetchall()
    routing_map: Dict[str, Tuple[int, int]] = {
        str(r.shop_id): (int(r.fallback_times or 0), int(r.total_routing or 0)) for r in r_rows
    }

    shops: List[OutboundShopMetric] = []
    for r in rows:
        shop_id = str(r.shop_id)
        total = int(r.total_orders or 0)
        success = int(r.success_orders or 0)
        if total > 0:
            success_rate = round(success * 100.0 / total, 2)
        else:
            success_rate = 0.0

        fb_times, fb_total = routing_map.get(shop_id, (0, 0))
        if fb_total > 0:
            fb_rate = round(fb_times * 100.0 / fb_total, 2)
        else:
            fb_rate = 0.0

        shops.append(
            OutboundShopMetric(
                shop_id=shop_id,
                total_orders=total,
                success_orders=success,
                success_rate=success_rate,
                fallback_times=fb_times,
                fallback_rate=fb_rate,
            )
        )

    return OutboundShopMetricsResponse(
        day=day,
        platform=platform,
        shops=shops,
    )
