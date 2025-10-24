# app/obs/metrics.py
# 来源基于你上传的版本，新增 outbound_commit_total 计数器。  :contentReference[oaicite:3]{index=3}
import time

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

http_requests_total = Counter("http_requests_total", "HTTP requests", ["method", "path", "code"])
http_request_duration = Histogram(
    "http_request_duration_seconds", "HTTP request duration seconds", ["method", "path"]
)
app_db_errors_total = Counter("app_db_errors_total", "DB errors total", ["op"])
wms_inventory_mismatch_total = Counter(
    "wms_inventory_mismatch_total", "Detected mismatches", ["type"]
)
celery_active_tasks = Gauge("celery_active_tasks", "Celery active tasks")

# 新增：出库吞吐量（每次“成功提交事务”+1；Grafana 用 rate() 看吞吐）
outbound_commit_total = Counter("outbound_commit_total", "Outbound commit count")

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        http_requests_total.labels(
            request.method, request.url.path, str(response.status_code)
        ).inc()
        http_request_duration.labels(request.method, request.url.path).observe(elapsed)
        return response
