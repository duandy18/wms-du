# app/infra/metrics.py
from __future__ import annotations
import os
from time import perf_counter
from typing import Callable, Optional
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

METRICS_ENABLED = os.getenv("METRICS_ENABLED", "1") not in ("0", "false", "False")

putaway_latency = Histogram("wms_putaway_latency_ms", "Putaway end-to-end latency (ms)")
inbound_latency = Histogram("wms_inbound_latency_ms", "Inbound end-to-end latency (ms)")
db_slow_sql = Counter("wms_db_slow_sql_count", "Slow SQL samples")

def time_block(hist: Histogram):
    def deco(fn: Callable):
        async def inner(*a, **kw):
            t0 = perf_counter()
            try:
                return await fn(*a, **kw)
            finally:
                dt_ms = (perf_counter() - t0) * 1000.0
                hist.observe(dt_ms)
        return inner
    return deco

def metrics_endpoint():
    if not METRICS_ENABLED:
        from fastapi import Response
        return Response(status_code=204)
    from fastapi import Response
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
