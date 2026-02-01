# tests/api/test_metrics_shipping_quote_failures.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api._helpers_shipping_quote import auth_headers, login, pick_warehouse_id, require_env


@pytest.fixture(scope="module")
def client() -> TestClient:
    require_env()
    return TestClient(app)


def test_metrics_shipping_quote_failures_collects_quote_calc_reject(client: TestClient) -> None:
    token = login(client)
    h = auth_headers(token)

    wid = pick_warehouse_id(client, token)

    # 触发一次 QUOTE_CALC_REJECT（scheme 不存在）
    r = client.post(
        "/shipping-quote/calc",
        headers=h,
        json={
            "warehouse_id": wid,
            "scheme_id": 999999,
            "dest": {
                "province": "北京市",
                "city": "北京市",
                "district": None,
                "province_code": "110000",
                "city_code": "110100",
            },
            "real_weight_kg": 1.0,
            "flags": [],
        },
    )
    assert r.status_code == 422, r.text

    detail = r.json()["detail"]
    assert isinstance(detail, dict), r.text
    assert detail["code"] == "QUOTE_CALC_SCHEME_NOT_FOUND"

    # 查询当日 failures（UTC day 由服务端取 created_at 统计；这里用固定 day 可能受时区影响）
    # 为保证稳定，这里用 /metrics/shipping-quote/failures 的 day=今天（UTC）：
    from datetime import datetime, timezone

    day = datetime.now(timezone.utc).date().isoformat()

    m = client.get(f"/metrics/shipping-quote/failures?day={day}&limit=50", headers=h)
    assert m.status_code == 200, m.text
    body = m.json()

    assert int(body["calc_failed_total"]) >= 1
    assert int(body["calc_failures_by_code"].get("QUOTE_CALC_SCHEME_NOT_FOUND", 0)) >= 1
