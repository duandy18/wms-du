# tests/api/test_shipping_quote_calc_api.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests._problem import as_problem
from tests.api._helpers_shipping_quote import (
    auth_headers,
    create_scheme_bundle,
    login,
    pick_warehouse_id,
    require_env,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    require_env()
    return TestClient(app)


def test_shipping_quote_calc_flat_and_surcharge(client: TestClient) -> None:
    token = login(client)
    ids = create_scheme_bundle(client, token)
    wid = pick_warehouse_id(client, token)

    r = client.post(
        "/shipping-quote/calc",
        headers=auth_headers(token),
        json={
            "warehouse_id": wid,
            "scheme_id": ids["scheme_id"],
            "dest": {
                "province": "北京市",
                "city": "北京市",
                "district": "朝阳区",
                "province_code": "110000",
                "city_code": "110100",
            },
            "real_weight_kg": 0.8,
            "flags": [],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["quote_status"] == "OK"
    assert body["weight"]["billable_weight_kg"] == 1.0
    assert body["breakdown"]["base"]["kind"] == "flat"
    assert abs(float(body["breakdown"]["base"]["amount"]) - 2.5) < 1e-9
    assert abs(float(body["total_amount"]) - 4.0) < 1e-9

    reasons = body.get("reasons") or []
    assert any("quote_engine: legacy" in x for x in reasons)
    assert any("level3_compare: match" in x for x in reasons)


def test_shipping_quote_calc_linear_total(client: TestClient) -> None:
    token = login(client)
    ids = create_scheme_bundle(client, token)
    wid = pick_warehouse_id(client, token)

    r = client.post(
        "/shipping-quote/calc",
        headers=auth_headers(token),
        json={
            "warehouse_id": wid,
            "scheme_id": ids["scheme_id"],
            "dest": {
                "province": "北京市",
                "city": "北京市",
                "district": "朝阳区",
                "province_code": "110000",
                "city_code": "110100",
            },
            "real_weight_kg": 3.6,
            "flags": [],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["quote_status"] == "OK"
    assert body["weight"]["billable_weight_kg"] == 4.0
    base = float(body["breakdown"]["base"]["amount"])
    assert abs(base - 7.8) < 1e-9
    assert abs(float(body["total_amount"]) - 9.3) < 1e-9

    reasons = body.get("reasons") or []
    assert any("quote_engine: legacy" in x for x in reasons)
    assert any("level3_compare: match" in x for x in reasons)


def test_shipping_quote_calc_returns_legacy_contract_shape_with_shadow_compare(client: TestClient) -> None:
    token = login(client)
    ids = create_scheme_bundle(client, token)
    wid = pick_warehouse_id(client, token)

    r = client.post(
        "/shipping-quote/calc",
        headers=auth_headers(token),
        json={
            "warehouse_id": wid,
            "scheme_id": ids["scheme_id"],
            "dest": {
                "province": "北京市",
                "city": "北京市",
                "district": "海淀区",
                "province_code": "110000",
                "city_code": "110100",
            },
            "real_weight_kg": 1.2,
            "flags": [],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["ok"] is True
    assert body["quote_status"] == "OK"

    zone = body.get("zone")
    assert isinstance(zone, dict)
    assert "id" in zone
    assert "name" in zone
    assert zone.get("source") == "legacy"

    bracket = body.get("bracket")
    assert isinstance(bracket, dict)
    assert "id" in bracket
    assert "pricing_mode" in bracket
    assert bracket.get("source") == "legacy"

    breakdown = body.get("breakdown") or {}
    assert isinstance(breakdown.get("base"), dict)
    assert isinstance(breakdown.get("surcharges"), list)
    assert isinstance((breakdown.get("summary") or {}), dict)

    reasons = body.get("reasons") or []
    assert any("level3_compare:" in x for x in reasons)


def test_shipping_quote_calc_error_code_scheme_not_found(client: TestClient) -> None:
    token = login(client)
    wid = pick_warehouse_id(client, token)

    r = client.post(
        "/shipping-quote/calc",
        headers=auth_headers(token),
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
    p = as_problem(r.json())
    assert p["error_code"] == "QUOTE_CALC_SCHEME_NOT_FOUND"
