# tests/smoke/test_monitor_metrics_pg.py
import os
import time
import urllib.request
import json

# 默认 8000；本地运行 make smoke 时会由环境变量固定到 8001
API = os.getenv("API_BASE", "http://127.0.0.1:8000")

def _http_json(url: str, method="GET", body=None, timeout=5):
    """简易 HTTP JSON 请求（用于 /ping 等 JSON 接口）"""
    req = urllib.request.Request(url, method=method)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
        ctype = r.getheader("Content-Type") or ""
        text = r.read().decode("utf-8")
        return json.loads(text) if "application/json" in ctype else text

def _http_text(url: str, timeout=5) -> str:
    """始终按文本读取（用于 /metrics 的 text/plain 暴露）"""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8")

def test_metrics_smoke_and_event_counter():
    # 1) API 健康
    pong = _http_json(f"{API}/ping")
    assert isinstance(pong, dict) and pong.get("pong") is True

    # 2) 触发一条合法事件（None -> PAID），order_no 每次唯一，避免被快照历史影响
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

    # 3) 拉取 /metrics，确认业务计数器出现（text/plain，按文本匹配）
    # 给导出器/聚合 1~2s
    time.sleep(2)
    metrics_text = _http_text(f"{API}/metrics")
    assert "events_processed_total" in metrics_text
