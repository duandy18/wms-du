# app/services/shipping_quote_metrics_failures.py
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.metrics_shipping_quote import (
    ShippingQuoteFailureDetail,
    ShippingQuoteFailuresMetricsResponse,
)


def _bump(counter: Dict[str, int], key: str, inc: int = 1) -> None:
    k = (key or "").strip() or "UNKNOWN"
    counter[k] = int(counter.get(k, 0)) + int(inc)


async def load_shipping_quote_failures(
    session: AsyncSession,
    *,
    day: date,
    platform: Optional[str] = None,
    limit: int = 200,
) -> ShippingQuoteFailuresMetricsResponse:
    """
    Shipping Quote 失败面板：
    - 来源：audit_events（category='SHIPPING_QUOTE'）
    - 事件：QUOTE_CALC_REJECT / QUOTE_RECOMMEND_REJECT
    - 统计：按 error_code 聚合 + 明细（默认最多 200 条）
    """
    sql = text(
        """
        SELECT
          ref,
          meta->>'event' AS event,
          COALESCE(meta->>'error_code','') AS error_code,
          COALESCE(meta->>'message','') AS message,
          to_char(created_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS created_at
        FROM audit_events
        WHERE category = 'SHIPPING_QUOTE'
          AND (meta->>'event') IN ('QUOTE_CALC_REJECT','QUOTE_RECOMMEND_REJECT')
          AND (created_at AT TIME ZONE 'utc')::date = :day
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )
    rows = (await session.execute(sql, {"day": day, "limit": int(limit)})).fetchall()

    calc_total = 0
    rec_total = 0
    calc_by_code: Dict[str, int] = {}
    rec_by_code: Dict[str, int] = {}
    details: List[ShippingQuoteFailureDetail] = []

    for r in rows:
        ev = (r.event or "").strip()
        code = (r.error_code or "").strip() or "UNKNOWN"
        msg = (r.message or "").strip() or None

        if ev == "QUOTE_CALC_REJECT":
            calc_total += 1
            _bump(calc_by_code, code)
        elif ev == "QUOTE_RECOMMEND_REJECT":
            rec_total += 1
            _bump(rec_by_code, code)

        details.append(
            ShippingQuoteFailureDetail(
                ref=r.ref,
                event=ev or "UNKNOWN",
                error_code=code,
                message=msg,
                created_at=r.created_at,
            )
        )

    return ShippingQuoteFailuresMetricsResponse(
        day=day,
        platform=platform,
        calc_failed_total=calc_total,
        recommend_failed_total=rec_total,
        calc_failures_by_code=calc_by_code,
        recommend_failures_by_code=rec_by_code,
        details=details,
    )
