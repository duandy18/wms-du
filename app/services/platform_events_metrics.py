# app/services/platform_events_metrics.py
from __future__ import annotations

from app.metrics import ERRS, EVENTS


def inc_event_metric(platform: str, shop_id: str, state: str) -> None:
    EVENTS.labels(
        (platform or "").lower(),
        shop_id or "",
        (state or "").upper() or "UNKNOWN",
    ).inc()


def inc_error_metric(platform: str, shop_id: str, code: str) -> None:
    ERRS.labels(
        (platform or "").lower(),
        shop_id or "",
        code or "ERROR",
    ).inc()
