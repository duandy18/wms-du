# app/oms/services/platform_events_metrics.py
from __future__ import annotations

from app.metrics import ERRS, EVENTS


def inc_event_metric(platform: str, store_code: str, state: str) -> None:
    EVENTS.labels(
        (platform or "").lower(),
        store_code or "",
        (state or "").upper() or "UNKNOWN",
    ).inc()


def inc_error_metric(platform: str, store_code: str, code: str) -> None:
    ERRS.labels(
        (platform or "").lower(),
        store_code or "",
        code or "ERROR",
    ).inc()
