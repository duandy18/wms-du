# app/metrics.py
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

try:
    # multiprocess 支持（需在进程启动前设置好 PROMETHEUS_MULTIPROC_DIR）
    from prometheus_client import REGISTRY, CollectorRegistry, multiprocess

    _HAVE_MP = True
except Exception:  # 兼容无 multiprocess 环境
    from prometheus_client import REGISTRY

    _HAVE_MP = False

# 业务指标（注意：需要在进程启动且 env 已设置后再 import 本模块）
EVENTS = Counter("events_processed_total", "Events processed", ["platform", "shop_id", "state"])
ERRS = Counter("event_errors_total", "Event errors", ["platform", "shop_id", "code"])
OUTB = Counter("outbound_committed_total", "Outbound commits", ["platform", "shop_id"])
LAT = Histogram(
    "event_latency_seconds", "Event latency (seconds)", ["platform", "shop_id", "state"]
)

router = new_router = APIRouter()


@router.get("/metrics")
def metrics() -> Response:
    """
    在单进程模式下直接导出默认 REGISTRY；
    在多进程模式下，创建临时 CollectorRegistry，并让 MultiProcessCollector 合并 /prom-data 下各分片。
    """
    if _HAVE_MP and os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        payload = generate_latest(registry)
    else:
        payload = generate_latest(REGISTRY)
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
