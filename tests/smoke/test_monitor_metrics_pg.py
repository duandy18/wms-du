import os
import time
import urllib.request
import json
import subprocess
import shlex
from urllib.parse import urlparse
import pytest

API = os.getenv("API_BASE", "http://127.0.0.1:8000")

def _http_json(url: str, method="GET", body=None, timeout=5):
    req = urllib.request.Request(url, method=method)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
        ctype = r.getheader("Content-Type") or ""
        txt = r.read().decode("utf-8")
        return json.loads(txt) if "application/json" in ctype else txt

def _http_text(url: str, timeout=5) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")

def _ensure_api_up():
    try:
        _ = _http_json(f"{API}/ping")
        return None
    except Exception:
        pass
    url = urlparse(API)
    host = url.hostname or "127.0.0.1"
    port = url.port or 8000
    cmd = f"python -m uvicorn app.main:app --host {host} --port {port}"
    proc = subprocess.Popen(shlex.split(cmd))
    for _ in range(20):
        try:
            time.sleep(0.5)
            if _http_json(f"{API}/ping").get("pong"):
                return proc
        except Exception:
            continue
    raise RuntimeError("Failed to start API for smoke tests")

def _redis_ready() -> bool:
    def _can(url: str) -> bool:
        try:
            import redis  # from celery[redis]
            r = redis.Redis.from_url(url, socket_connect_timeout=1)
            r.ping()
            return True
        except Exception:
            return False
    broker = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    return _can(broker) and _can(backend)

def test_metrics_smoke_and_event_counter():
    _ensure_api_up()
    assert _http_json(f"{API}/ping").get("pong") is True

    if not _redis_ready():
        pytest.skip("Redis broker/backend unavailable; skip Celery smoke.")

    from app.worker import celery
    order_no = f"SMK-{int(time.time()*1000)}"
    r = celery.send_task(
        "wms.process_event",
        kwargs={"platform":"tmall","shop_id":"smoke-1",
                "payload":{"order_no":order_no,"to_state":"PAID"}}
    )
    assert r.get(timeout=60) == "OK"

    time.sleep(2)
    metrics_text = _http_text(f"{API}/metrics")
    assert "events_processed_total" in metrics_text
