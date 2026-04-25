# app/tms/quote/metrics/routes_failures.py
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.contracts.metrics_shipping_quote import ShippingQuoteFailuresMetricsResponse
from app.db.deps import get_async_session as get_session
from app.tms.quote.metrics.failures import load_shipping_quote_failures


def register(router: APIRouter) -> None:
    @router.get(
        "/metrics/shipping-assist/shipping/quote/failures",
        response_model=ShippingQuoteFailuresMetricsResponse,
    )
    async def get_shipping_quote_failures(
        day: date = Query(..., description="UTC date, format YYYY-MM-DD"),
        platform: str | None = Query(None),
        limit: int = Query(200, ge=1, le=500),
        session: AsyncSession = Depends(get_session),
    ) -> ShippingQuoteFailuresMetricsResponse:
        return await load_shipping_quote_failures(
            session,
            day=day,
            platform=platform,
            limit=limit,
        )
