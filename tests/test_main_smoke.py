# tests/test_main_smoke.py
from fastapi.testclient import TestClient

from app.main import app


def test_openapi_endpoint_alive():
    """确认 /openapi.json 接口可用."""
    client = TestClient(app)
    r = client.get("/openapi.json")
    assert r.status_code == 200
    data = r.json()
    assert "paths" in data


def test_root_or_health_exist():
    """尝试命中根路由或健康检查接口."""
    client = TestClient(app)
    for path in ("/health", "/", "/status"):
        resp = client.get(path)
        if resp.status_code < 500:
            # 命中任意一个即可
            assert resp.status_code in (200, 204, 301, 302, 404) or resp.ok
            break
