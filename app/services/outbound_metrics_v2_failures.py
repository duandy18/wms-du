# app/services/outbound_metrics_v2_failures.py
from __future__ import annotations

from datetime import date
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_outbound_v2 import OutboundFailureDetail, OutboundFailuresMetricsResponse


def _bump(counter: Dict[str, int], key: str, inc: int = 1) -> None:
    k = (key or "").strip() or "UNKNOWN"
    counter[k] = int(counter.get(k, 0)) + int(inc)


async def load_failures(
    session: AsyncSession,
    *,
    day: date,
    platform: str,
) -> OutboundFailuresMetricsResponse:
    """
    出库失败诊断（v2，PROD-only 简化口径）：

    ✅ 默认排除测试店铺（store_id 级别门禁）。
    """
    fail_sql = text(
        """
        SELECT
            ref,
            meta->>'trace_id' AS trace_id,

            CASE
              WHEN category = 'OUTBOUND' AND (meta->>'event') = 'SHIP_CONFIRM_REJECT'
                THEN 'SHIP_FAIL'
              ELSE COALESCE(meta->>'fail_point', '')
            END AS fail_point,

            COALESCE(meta->>'error_code', '') AS error_code,

            CASE
              WHEN category = 'OUTBOUND' AND (meta->>'event') = 'SHIP_CONFIRM_REJECT'
                THEN CONCAT(COALESCE(meta->>'error_code',''), ': ', COALESCE(meta->>'message',''))
              ELSE COALESCE(meta->>'message', '')
            END AS message
        FROM audit_events
        WHERE (
              (category IN ('OUTBOUND_FAIL','ROUTING'))
           OR (category = 'OUTBOUND' AND (meta->>'event') = 'SHIP_CONFIRM_REJECT')
        )
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
        """
    )
    rows = (await session.execute(fail_sql, {"platform": platform, "day": day})).fetchall()

    routing_failed = 0
    pick_failed = 0
    ship_failed = 0
    inventory_insufficient = 0
    details: List[OutboundFailureDetail] = []

    routing_by_code: Dict[str, int] = {}
    pick_by_code: Dict[str, int] = {}
    ship_by_code: Dict[str, int] = {}
    inv_by_code: Dict[str, int] = {}

    for r in rows:
        fail_point_raw = (r.fail_point or "").upper()
        code_raw = (r.error_code or "").strip() or "UNKNOWN"

        if fail_point_raw == "ROUTING_FAIL":
            routing_failed += 1
            _bump(routing_by_code, code_raw)
            fail_point = "ROUTING_FAIL"
        elif fail_point_raw == "PICK_FAIL":
            pick_failed += 1
            _bump(pick_by_code, code_raw)
            fail_point = "PICK_FAIL"
        elif fail_point_raw == "SHIP_FAIL":
            ship_failed += 1
            _bump(ship_by_code, code_raw)
            fail_point = "SHIP_FAIL"
        elif fail_point_raw == "INVENTORY_FAIL":
            inventory_insufficient += 1
            _bump(inv_by_code, code_raw)
            fail_point = "INVENTORY_FAIL"
        else:
            fail_point = fail_point_raw or "UNKNOWN"

        details.append(
            OutboundFailureDetail(
                ref=r.ref,
                trace_id=r.trace_id,
                fail_point=fail_point,
                message=r.message,
            )
        )

    return OutboundFailuresMetricsResponse(
        day=day,
        platform=platform,
        routing_failed=routing_failed,
        pick_failed=pick_failed,
        ship_failed=ship_failed,
        inventory_insufficient=inventory_insufficient,
        routing_failures_by_code=routing_by_code,
        pick_failures_by_code=pick_by_code,
        ship_failures_by_code=ship_by_code,
        inventory_failures_by_code=inv_by_code,
        details=details,
    )
