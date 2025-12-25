# tests/api/test_shipping_quote_pricing_api.py
from __future__ import annotations

import os
from typing import Dict, Optional

import pytest
from fastapi.testclient import TestClient

from app.main import app


def _require_env() -> None:
    if not (os.getenv("WMS_DATABASE_URL") or os.getenv("WMS_TEST_DATABASE_URL")):
        raise RuntimeError("WMS_TEST_DATABASE_URL / WMS_DATABASE_URL 未设置（Makefile 应该已注入）")


@pytest.fixture(scope="module")
def client() -> TestClient:
    _require_env()
    return TestClient(app)


def _login(client: TestClient, username: str = "admin", password: str = "admin123") -> str:
    r = client.post("/users/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token
    return token


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_scheme_bundle(client: TestClient, token: str) -> Dict[str, int]:
    """
    在测试库里创建一套最小可算的 scheme：
    provider(已存在 id=1) -> scheme -> zone_atomic -> brackets + surcharge
    """
    h = _auth_headers(token)

    # 1) provider 取一个存在的（dev 库通常有 id=1）
    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_id = int(pdata[0]["id"])

    # 2) create scheme
    sr = client.post(
        f"/shipping-providers/{provider_id}/pricing-schemes",
        headers=h,
        json={
            "name": "TEST-PRICING-SCHEME",
            "active": True,
            "priority": 100,
            "currency": "CNY",
            "billable_weight_rule": {"rounding": {"mode": "ceil", "step_kg": 1.0}},
        },
    )
    assert sr.status_code == 201, sr.text
    scheme_id = int(sr.json()["data"]["id"])

    # 3) create zone atomic
    zr = client.post(
        f"/pricing-schemes/{scheme_id}/zones-atomic",
        headers=h,
        json={
            "name": "北京市、天津市、河北省",
            "priority": 100,
            "active": True,
            "provinces": ["北京市", "天津市", "河北省"],
        },
    )
    assert zr.status_code == 201, zr.text
    zone_id = int(zr.json()["id"])

    # 4) create brackets (0-1, 1.01-2, 2.01-3 flat)
    for b in [
        {"min_kg": 0.0, "max_kg": 1.0, "pricing_mode": "flat", "flat_amount": 2.5, "active": True},
        {"min_kg": 1.01, "max_kg": 2.0, "pricing_mode": "flat", "flat_amount": 3.8, "active": True},
        {"min_kg": 2.01, "max_kg": 3.0, "pricing_mode": "flat", "flat_amount": 4.8, "active": True},
        {"min_kg": 3.01, "max_kg": 30.0, "pricing_mode": "linear_total", "base_amount": 3.0, "rate_per_kg": 1.2, "active": True},
        {"min_kg": 30.01, "max_kg": None, "pricing_mode": "linear_total", "base_amount": 3.0, "rate_per_kg": 1.5, "active": True},
    ]:
        br = client.post(f"/zones/{zone_id}/brackets", headers=h, json=b)
        assert br.status_code == 201, br.text

    # 5) create surcharge (北京 +1.5)
    sur = client.post(
        f"/pricing-schemes/{scheme_id}/surcharges",
        headers=h,
        json={
            "name": "目的地附加费-北京市",
            "priority": 100,
            "active": True,
            "condition_json": {"dest": {"province": ["北京市"]}},
            "amount_json": {"kind": "flat", "amount": 1.5},
        },
    )
    assert sur.status_code == 201, sur.text

    return {"provider_id": provider_id, "scheme_id": scheme_id, "zone_id": zone_id}


def test_shipping_quote_calc_flat_and_surcharge(client: TestClient) -> None:
    token = _login(client)
    ids = _create_scheme_bundle(client, token)

    r = client.post(
        "/shipping-quote/calc",
        headers=_auth_headers(token),
        json={
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
    assert abs(float(body["total_amount"]) - 4.0) < 1e-9  # 2.5 + 1.5 surcharge


def test_shipping_quote_calc_linear_total(client: TestClient) -> None:
    token = _login(client)
    ids = _create_scheme_bundle(client, token)

    r = client.post(
        "/shipping-quote/calc",
        headers=_auth_headers(token),
        json={
            "scheme_id": ids["scheme_id"],
            "dest": {"province": "北京市", "city": "北京市", "district": "朝阳区"},
            "real_weight_kg": 3.6,  # billable -> 4
            "flags": [],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["quote_status"] == "OK"
    assert body["weight"]["billable_weight_kg"] == 4.0
    base = float(body["breakdown"]["base"]["amount"])
    assert abs(base - 7.8) < 1e-9  # 3 + 1.2*4
    assert abs(float(body["total_amount"]) - 9.3) < 1e-9  # +1.5
