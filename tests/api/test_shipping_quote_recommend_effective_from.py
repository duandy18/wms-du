# tests/api/test_shipping_quote_recommend_effective_from.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api._helpers_shipping_quote import (
    auth_headers,
    clear_warehouse_bindings,
    create_template_bundle_for_provider,
    login,
    pick_warehouse_id,
    require_env,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    require_env()
    return TestClient(app)


def _recommend(
    client: TestClient,
    token: str,
    *,
    warehouse_id: int,
) -> dict:
    h = auth_headers(token)
    rr = client.post(
        "/shipping-quote/recommend",
        headers=h,
        json={
            "warehouse_id": warehouse_id,
            "provider_ids": [],
            "dest": {
                "province": "河北省",
                "city": "廊坊市",
                "district": "固安县",
                "province_code": "130000",
                "city_code": "131000",
            },
            "real_weight_kg": 1.0,
            "flags": [],
            "max_results": 10,
        },
    )
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert body["ok"] is True
    return body


def test_shipping_quote_recommend_excludes_scheduled_binding(client: TestClient) -> None:
    token = login(client)
    h = auth_headers(token)

    wid = pick_warehouse_id(client, token)
    clear_warehouse_bindings(client, token, wid)

    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_id = int(pdata[0]["id"])

    ids = create_template_bundle_for_provider(
        client,
        token,
        provider_id,
        name_suffix="EFFECTIVE-FUTURE",
    )

    deactivate_resp = client.post(
        f"/tms/pricing/warehouses/{wid}/bindings/{provider_id}/deactivate",
        headers=h,
        json={},
    )
    assert deactivate_resp.status_code == 200, deactivate_resp.text

    future_time = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
    activate_resp = client.post(
        f"/tms/pricing/warehouses/{wid}/bindings/{provider_id}/activate",
        headers=h,
        json={"effective_from": future_time},
    )
    assert activate_resp.status_code == 200, activate_resp.text
    activate_body = activate_resp.json()
    assert activate_body["ok"] is True
    assert activate_body["data"]["runtime_status"] == "scheduled"

    body = _recommend(
        client,
        token,
        warehouse_id=wid,
    )
    assert body["quotes"] == []
    assert body["recommended_template_id"] is None


def test_shipping_quote_recommend_includes_active_binding(client: TestClient) -> None:
    token = login(client)
    h = auth_headers(token)

    wid = pick_warehouse_id(client, token)
    clear_warehouse_bindings(client, token, wid)

    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_id = int(pdata[0]["id"])

    ids = create_template_bundle_for_provider(
        client,
        token,
        provider_id,
        name_suffix="EFFECTIVE-ACTIVE",
    )

    body = _recommend(
        client,
        token,
        warehouse_id=wid,
    )
    quotes = body["quotes"]
    assert quotes, body
    assert body["recommended_template_id"] is not None
    assert any(int(q["template_id"]) == int(ids["template_id"]) for q in quotes)
    assert any(int(q["provider_id"]) == int(provider_id) for q in quotes)
