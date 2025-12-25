# tests/api/test_zone_brackets_constraints_and_copy.py
from __future__ import annotations

import os
from typing import Dict

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


def _create_scheme_zone(client: TestClient, token: str, zone_name: str, provinces: list[str]) -> Dict[str, int]:
    h = _auth_headers(token)
    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    provider_id = int(pr.json()["data"][0]["id"])

    sr = client.post(
        f"/shipping-providers/{provider_id}/pricing-schemes",
        headers=h,
        json={
            "name": f"TEST-COPY-{zone_name}",
            "active": True,
            "priority": 100,
            "currency": "CNY",
            "billable_weight_rule": {"rounding": {"mode": "ceil", "step_kg": 1.0}},
        },
    )
    assert sr.status_code == 201, sr.text
    scheme_id = int(sr.json()["data"]["id"])

    zr = client.post(
        f"/pricing-schemes/{scheme_id}/zones-atomic",
        headers=h,
        json={
            "name": zone_name,
            "priority": 100,
            "active": True,
            "provinces": provinces,
        },
    )
    assert zr.status_code == 201, zr.text
    zone_id = int(zr.json()["id"])
    return {"scheme_id": scheme_id, "zone_id": zone_id}


def test_bracket_unique_range_conflict_returns_409(client: TestClient) -> None:
    token = _login(client)
    h = _auth_headers(token)
    ids = _create_scheme_zone(client, token, "模板Zone", ["北京市"])

    # create first bracket
    r1 = client.post(
        f"/zones/{ids['zone_id']}/brackets",
        headers=h,
        json={"min_kg": 0.0, "max_kg": 1.0, "pricing_mode": "flat", "flat_amount": 2.5, "active": True},
    )
    assert r1.status_code == 201, r1.text

    # create duplicate bracket -> must be 409
    r2 = client.post(
        f"/zones/{ids['zone_id']}/brackets",
        headers=h,
        json={"min_kg": 0.0, "max_kg": 1.0, "pricing_mode": "flat", "flat_amount": 2.6, "active": True},
    )
    assert r2.status_code == 409, r2.text
    assert "min_kg/max_kg conflict" in r2.text


def test_copy_zone_brackets_api(client: TestClient) -> None:
    token = _login(client)
    h = _auth_headers(token)

    ids_src = _create_scheme_zone(client, token, "源Zone", ["北京市"])
    ids_tgt = _create_scheme_zone(client, token, "目标Zone", ["天津市"])

    # 让它们属于同一个 scheme：为了简单，直接在同一个 scheme 下再建 target zone
    # 重新建一个 target zone（同 scheme）
    zr = client.post(
        f"/pricing-schemes/{ids_src['scheme_id']}/zones-atomic",
        headers=h,
        json={
            "name": "目标Zone(同scheme)",
            "priority": 110,
            "active": True,
            "provinces": ["天津市"],
        },
    )
    assert zr.status_code == 201, zr.text
    target_zone_id = int(zr.json()["id"])

    # 源 zone 录入 2 条 bracket
    for b in [
        {"min_kg": 0.0, "max_kg": 1.0, "pricing_mode": "flat", "flat_amount": 2.5, "active": True},
        {"min_kg": 3.01, "max_kg": 30.0, "pricing_mode": "linear_total", "base_amount": 3.0, "rate_per_kg": 1.2, "active": True},
    ]:
        rr = client.post(f"/zones/{ids_src['zone_id']}/brackets", headers=h, json=b)
        assert rr.status_code == 201, rr.text

    # copy
    cr = client.post(
        f"/zones/{target_zone_id}/brackets:copy",
        headers=h,
        json={
            "source_zone_id": ids_src["zone_id"],
            "conflict_policy": "skip",
            "active_policy": "force_active",
            "pricing_modes": ["flat", "linear_total"],
            "include_inactive": False,
        },
    )
    assert cr.status_code == 200, cr.text
    out = cr.json()
    assert out["ok"] is True
    assert out["summary"]["created_count"] == 2
    assert out["summary"]["failed_count"] == 0
