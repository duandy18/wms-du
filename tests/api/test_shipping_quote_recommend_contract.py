# tests/api/test_shipping_quote_recommend_contract.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api._helpers_shipping_quote import (
    auth_headers,
    bind_provider_to_warehouse,
    clear_warehouse_bindings,
    create_template_bundle_for_provider,
    ensure_second_provider,
    login,
    pick_warehouse_id,
    require_env,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    require_env()
    return TestClient(app)


def _assert_quote_snapshot_shape(snapshot: object) -> None:
    assert isinstance(snapshot, dict)
    assert snapshot.get("version") == "v1"
    assert isinstance(snapshot.get("source"), str)

    input_payload = snapshot.get("input")
    assert isinstance(input_payload, dict)

    selected_quote = snapshot.get("selected_quote")
    assert isinstance(selected_quote, dict)

    total_amount = selected_quote.get("total_amount")
    assert isinstance(total_amount, (int, float))

    reasons = selected_quote.get("reasons")
    assert isinstance(reasons, list)
    assert len(reasons) > 0


def test_shipping_quote_recommend_respects_warehouse_bound_candidates_phase3(client: TestClient) -> None:
    token = login(client)
    h = auth_headers(token)

    wid = pick_warehouse_id(client, token)
    clear_warehouse_bindings(client, token, wid)

    pr = client.get("/shipping-assist/pricing/providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_a = int(pdata[0]["id"])

    ids_a = create_template_bundle_for_provider(client, token, provider_a, name_suffix="A")
    cr = client.post(
        "/shipping-assist/shipping/quote/calc",
        headers=h,
        json={
            "warehouse_id": wid,
            "template_id": ids_a["template_id"],
            "dest": {
                "province": "河北省",
                "city": "廊坊市",
                "district": "固安县",
                "province_code": "130000",
                "city_code": "131000",
            },
            "real_weight_kg": 1.0,
            "flags": [],
        },
    )
    assert cr.status_code == 200, cr.text
    calc_body = cr.json()
    assert calc_body["quote_status"] == "OK"
    assert "destination_group" in calc_body
    assert "pricing_matrix" in calc_body
    assert "quote_snapshot" in calc_body
    _assert_quote_snapshot_shape(calc_body["quote_snapshot"])

    rr = client.post(
        "/shipping-assist/shipping/quote/recommend",
        headers=h,
        json={
            "warehouse_id": wid,
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
    quotes = body["quotes"]
    assert quotes, "expected non-empty quotes when warehouse has enabled provider and bound template"
    assert all(int(q["provider_id"]) == provider_a for q in quotes)
    assert body["recommended_template_id"] is not None
    assert any(int(q["template_id"]) == ids_a["template_id"] for q in quotes)
    assert all("destination_group" in q for q in quotes)
    assert all("pricing_matrix" in q for q in quotes)

    for quote in quotes:
        assert quote["template_name"] is not None
        assert abs(float(quote["total_amount"])) >= 0

    first = quotes[0]
    assert int(first["template_id"]) == ids_a["template_id"]


def test_shipping_quote_recommend_provider_ids_intersect_warehouse_phase3(client: TestClient) -> None:
    token = login(client)
    h = auth_headers(token)

    wid = pick_warehouse_id(client, token)
    clear_warehouse_bindings(client, token, wid)

    pr = client.get("/shipping-assist/pricing/providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_a = int(pdata[0]["id"])

    ids_a2 = create_template_bundle_for_provider(client, token, provider_a, name_suffix="A2")
    assert ids_a2["template_id"] > 0

    provider_b = ensure_second_provider(client, token)

    rr = client.post(
        "/shipping-assist/shipping/quote/recommend",
        headers=h,
        json={
            "warehouse_id": wid,
            "provider_ids": [provider_b],
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
    assert body["quotes"] == []
    assert body["recommended_template_id"] is None
