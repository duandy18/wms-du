# tests/smoke/test_monitor_metrics_pg.py
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
    # 先试 /ping；连不上则临时起一个 uvicorn（仅在本进程期间存活）
    try:
        _ = _http_json(f"{API}/ping")
        return None  # 已经在跑
    except Exception:
        pass

    url = urlparse(API)
    host = url.hostname or "127.0.0.1"
    port = url.port or 8000
    cmd = f"python -m uvicorn app.main:app --host {host} --port {port}"
    proc = subprocess.Popen(shlex.split(cmd))
    # 等待最多 10s 起服务
    for _ in range(20):
        try:
            time.sleep(0.5)
            pong = _http_json(f"{API}/ping")
            if isinstance(pong, dict) and pong.get("pong") is True:
                return proc
        except Exception:
            continue
    raise RuntimeError("Failed to start API for smoke tests")

def _redis_ready() -> bool:
    """
    检测 Redis 是否可连接；不可用时跳过本用例。
    默认读取 CELERY_RESULT_BACKEND 或 REDIS_URL，回退到 localhost:6379。
    """
    url = os.getenv("CELERY_RESULT_BACKEND") or os.getenv("REDIS_URL") or "redis://localhost:6379/1"
    try:
        import redis  # 依赖由 celery[redis] 带入
        r = redis.Redis.from_url(url, socket_connect_timeout=1)
        r.ping()
        return True
    except Exception:
        return False

def test_metrics_smoke_and_event_counter():
    # 0) 确保 API 活着（本地/CI 任一环境）
    _ensure_api_up()

    # 1) API 健康
    pong = _http_json(f"{API}/ping")
    assert isinstance(pong, dict) and pong.get("pong") is True

    # 2) 如 Redis 不可用（某些 CI 任务场景），跳过 Celery 路径
    if not _redis_ready():
        pytest.skip("Redis backend/broker unavailable in this job; skip Celery smoke.")

    # 3) 触发一条合法事件（None -> PAID），order_no 唯一避免被快照历史影响
    from app.worker import celery
    order_no = f"SMK-{int(time.time() * 1000)}"
    r = celery.send_task(
        "wms.process_event",
        kwargs={
            "platform": "tmall",
            "shop_id": "smoke-1",
            "payload": {"order_no": order_no, "to_state": "PAID"},
        },
    )
    assert r.get(timeout=60) == "OK"

    # 4) 拉取 /metrics，确认业务计数器出现（text/plain，按文本匹配）
    time.sleep(2)
    metrics_text = _http_text(f"{API}/metrics")
    assert "events_processed_total" in metrics_text
