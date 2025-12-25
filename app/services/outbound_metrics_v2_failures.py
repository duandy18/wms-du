# app/services/outbound_metrics_v2_failures.py
from __future__ import annotations

from datetime import date
from typing import List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_outbound_v2 import OutboundFailureDetail, OutboundFailuresMetricsResponse


async def load_failures(
    session: AsyncSession,
    *,
    day: date,
    platform: str,
) -> OutboundFailuresMetricsResponse:
    fail_sql = text(
        """
        SELECT
            ref,
            meta->>'trace_id' AS trace_id,
            meta->>'fail_point' AS fail_point,
            meta->>'message' AS message
        FROM audit_events
        WHERE category IN ('OUTBOUND_FAIL','ROUTING')
          AND (meta->>'platform') = :platform
          AND (created_at AT TIME ZONE 'utc')::date = :day
        """
    )
    rows = (await session.execute(fail_sql, {"platform": platform, "day": day})).fetchall()

    routing_failed = 0
    pick_failed = 0
    ship_failed = 0
    inventory_insufficient = 0
    details: List[OutboundFailureDetail] = []

    for r in rows:
        fail_point_raw = (r.fail_point or "").upper()
        if fail_point_raw == "ROUTING_FAIL":
            routing_failed += 1
            fail_point = "ROUTING_FAIL"
        elif fail_point_raw == "PICK_FAIL":
            pick_failed += 1
            fail_point = "PICK_FAIL"
        elif fail_point_raw == "SHIP_FAIL":
            ship_failed += 1
            fail_point = "SHIP_FAIL"
        elif fail_point_raw == "INVENTORY_FAIL":
            inventory_insufficient += 1
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
        details=details,
    )
