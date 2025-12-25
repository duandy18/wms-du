# app/services/outbound_metrics_v2_range.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_outbound_v2 import OutboundDaySummary, OutboundRangeMetricsResponse
from app.services.outbound_metrics_v2_common import UTC
from app.services.outbound_metrics_v2_day import load_day


async def load_range(
    session: AsyncSession,
    *,
    platform: str,
    days: int,
    end_day: Optional[date] = None,
) -> OutboundRangeMetricsResponse:
    if end_day is None:
        end_day = datetime.now(UTC).date()

    day_list: List[date] = [end_day - timedelta(days=i) for i in range(days)]
    day_list.sort()

    summaries: List[OutboundDaySummary] = []
    for d in day_list:
        m = await load_day(session=session, day=d, platform=platform)
        summaries.append(
            OutboundDaySummary(
                day=m.day,
                total_orders=m.total_orders,
                success_rate=m.success_rate,
                fallback_rate=m.fallback_rate,
                fefo_hit_rate=m.fefo_hit_rate,
            )
        )

    return OutboundRangeMetricsResponse(platform=platform, days=summaries)
