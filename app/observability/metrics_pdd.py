from __future__ import annotations
from prometheus_client import Counter, Gauge

pdd_push_success = Counter("pdd_push_success_total", "Number of successful PDD inventory pushes", ["store_id"])
pdd_push_failure = Counter("pdd_push_failure_total", "Number of failed PDD inventory pushes", ["store_id"])
reserve_conflict = Counter("reserve_conflict_total", "Conflicts during reserve path", ["item_id"])
visible_drift = Gauge("visible_drift", "Platform vs system visible qty drift", ["store_id", "item_id"])
