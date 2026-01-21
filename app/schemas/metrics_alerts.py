# app/schemas/metrics_alerts.py
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AlertItem(BaseModel):
    severity: str  # INFO / WARN / CRIT
    domain: str  # OUTBOUND / SHIPPING_QUOTE
    code: str
    title: str
    message: str
    count: int
    threshold: Optional[int] = None
    meta: Dict[str, Any] = {}


class AlertsResponse(BaseModel):
    day: date
    platform: Optional[str] = None
    alerts: List[AlertItem] = []
