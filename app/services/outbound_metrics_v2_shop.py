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
                meta->>'shop_id' AS shop_id,
                meta->>'event' AS event,
                ref
            FROM audit_events
            WHERE category='OUTBOUND'
              AND (meta->>'platform') = :platform
              AND (created_at AT TIME ZONE 'utc')::date = :day
              AND (meta->>'shop_id') IS NOT NULL

              -- PROD-only：测试店铺门禁（store_id）
              AND NOT EXISTS (
                SELECT 1
                  FROM stores s
                  JOIN platform_test_shops pts
                    ON pts.store_id = s.id
                   AND pts.code = 'DEFAULT'
                 WHERE upper(s.platform) = upper(audit_events.meta->>'platform')
                   AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(audit_events.meta->>'shop_id' AS text))
              )
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
            meta->>'shop_id' AS shop_id,
            count(*) FILTER (WHERE meta->>'routing_event'='FALLBACK') AS fallback_times,
            count(*) FILTER (
                WHERE meta->>'routing_event' IN ('REQUEST','FALLBACK','OK')
            ) AS total_routing
        FROM audit_events
        WHERE category='ROUTING'
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
          AND (meta->>'shop_id') IS NOT NULL

          -- PROD-only：测试店铺门禁（store_id）
          AND NOT EXISTS (
            SELECT 1
              FROM stores s
              JOIN platform_test_shops pts
                ON pts.store_id = s.id
               AND pts.code = 'DEFAULT'
             WHERE upper(s.platform) = upper(audit_events.meta->>'platform')
               AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(audit_events.meta->>'shop_id' AS text))
          )
        GROUP BY shop_id
        """
    )
    r_rows = (await session.execute(routing_sql, {"platform": platform, "day": day})).fetchall()
    routing_map: Dict[str, Tuple[int, int]] = {
        str(r.shop_id): (int(r.fallback_times or 0), int(r.total_routing or 0)) for r in r_rows
    }

    shops: List[OutboundShopMetric] = []
    for r in rows:
        sid = str(r.shop_id)
        total = int(r.total_orders or 0)
        success = int(r.success_orders or 0)
        success_rate = round(success * 100.0 / total, 2) if total > 0 else 0.0

        fb_times, fb_total = routing_map.get(sid, (0, 0))
        fb_rate = round(fb_times * 100.0 / fb_total, 2) if fb_total > 0 else 0.0

        shops.append(
            OutboundShopMetric(
                shop_id=sid,
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
