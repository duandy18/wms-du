# app/schemas/metrics_shipping_quote.py
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel


class ShippingQuoteFailureDetail(BaseModel):
    ref: str
    event: str  # QUOTE_CALC_REJECT / QUOTE_RECOMMEND_REJECT
    error_code: str
    message: Optional[str] = None
    created_at: str  # ISO string


class ShippingQuoteFailuresMetricsResponse(BaseModel):
    day: date
    platform: Optional[str] = None  # 可选：如果未来要按平台过滤
    calc_failed_total: int
    recommend_failed_total: int
    calc_failures_by_code: Dict[str, int] = {}
    recommend_failures_by_code: Dict[str, int] = {}
    details: List[ShippingQuoteFailureDetail] = []
