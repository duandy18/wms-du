# tests/api/test_shipping_quote_calc_api.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api._helpers_shipping_quote import (
    auth_headers,
    bind_scheme_to_warehouse,
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

    bind_scheme_to_warehouse(client, token, ids["scheme_id"], wid)

    r = client.post(
        "/shipping-quote/calc",
        headers=auth_headers(token),
        json={
            "warehouse_id": wid,
            "scheme_id": ids["scheme_id"],
            "dest": {"province": "北京市", "city": "北京市", "district": "朝阳区"},
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


def test_shipping_quote_calc_linear_total(client: TestClient) -> None:
    token = login(client)
    ids = create_scheme_bundle(client, token)
    wid = pick_warehouse_id(client, token)

    bind_scheme_to_warehouse(client, token, ids["scheme_id"], wid)

    r = client.post(
        "/shipping-quote/calc",
        headers=auth_headers(token),
        json={
            "warehouse_id": wid,
            "scheme_id": ids["scheme_id"],
            "dest": {"province": "北京市", "city": "北京市", "district": "朝阳区"},
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


def test_shipping_quote_calc_error_code_scheme_not_found(client: TestClient) -> None:
    token = login(client)
    wid = pick_warehouse_id(client, token)

    r = client.post(
        "/shipping-quote/calc",
        headers=auth_headers(token),
        json={"warehouse_id": wid, "scheme_id": 999999, "dest": {"province": "北京市"}, "real_weight_kg": 1.0, "flags": []},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "QUOTE_CALC_SCHEME_NOT_FOUND"
