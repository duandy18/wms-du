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


def _pick_warehouse_id(client: TestClient, token: str) -> int:
    r = client.get("/warehouses", headers=_auth_headers(token))
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert rows, "no warehouses"
    return int(rows[0]["id"])


def _clear_warehouse_bindings(client: TestClient, token: str, warehouse_id: int) -> None:
    """
    Phase 2 测试可重复性：清空某仓库已有绑定（如果有）。
    """
    h = _auth_headers(token)
    r = client.get(f"/warehouses/{warehouse_id}/shipping-providers", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()["data"] or []
    for it in data:
        pid = int(it["shipping_provider_id"])
        dr = client.delete(f"/warehouses/{warehouse_id}/shipping-providers/{pid}", headers=h)
        # 已经不存在也无所谓，确保最终为空
        assert dr.status_code in (200, 404), dr.text


def _bind_provider_to_warehouse(client: TestClient, token: str, warehouse_id: int, provider_id: int) -> None:
    """
    Phase 2：仓库候选集事实绑定（Phase 1 API）。
    """
    h = _auth_headers(token)
    r = client.post(
        f"/warehouses/{warehouse_id}/shipping-providers/bind",
        headers=h,
        json={
            "shipping_provider_id": int(provider_id),
            "active": True,
            "priority": 0,
            "pickup_cutoff_time": "18:00",
            "remark": "test bind",
        },
    )
    assert r.status_code in (201, 409), r.text  # 已绑定会返回 409
    if r.status_code == 409:
        # 已存在则确保启用
        pr = client.patch(
            f"/warehouses/{warehouse_id}/shipping-providers/{provider_id}",
            headers=h,
            json={"active": True, "priority": 0},
        )
        assert pr.status_code == 200, pr.text


def _ensure_second_provider(client: TestClient, token: str) -> int:
    """
    Phase 2 兼容性测试需要第二个 provider：
    - 若已有 >=2 个，取第二个
    - 否则创建一个
    """
    h = _auth_headers(token)
    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"] or []
    if len(pdata) >= 2:
        return int(pdata[1]["id"])

    cr = client.post(
        "/shipping-providers",
        headers=h,
        json={
            "name": "TEST-PROVIDER-2",
            "code": "TP2",
            "active": True,
            "priority": 100,
            "pricing_model": None,
            "region_rules": None,
        },
    )
    assert cr.status_code == 201, cr.text
    return int(cr.json()["data"]["id"])


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


def _create_scheme_bundle_for_provider(client: TestClient, token: str, provider_id: int, *, name_suffix: str) -> Dict[str, int]:
    """
    为指定 provider 创建一套最小可算的 scheme（用于 Phase 2 的候选集/优先级测试）。
    """
    h = _auth_headers(token)

    sr = client.post(
        f"/shipping-providers/{provider_id}/pricing-schemes",
        headers=h,
        json={
            "name": f"TEST-PRICING-SCHEME-{name_suffix}",
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
            "name": f"河北省-TEST-{name_suffix}",
            "priority": 100,
            "active": True,
            "provinces": ["河北省"],
        },
    )
    assert zr.status_code == 201, zr.text
    zone_id = int(zr.json()["id"])

    # 单段兜底：0-inf linear_total（保证不会 no matching bracket）
    br = client.post(
        f"/zones/{zone_id}/brackets",
        headers=h,
        json={"min_kg": 0.0, "max_kg": None, "pricing_mode": "linear_total", "base_amount": 8.0, "rate_per_kg": 2.0, "active": True},
    )
    assert br.status_code == 201, br.text

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


def test_shipping_quote_recommend_respects_warehouse_bound_candidates_phase2(client: TestClient) -> None:
    """
    Phase 2 合同测试：
    - provider_ids 为空且提供 warehouse_id 时，候选集必须来自仓库绑定（事实），不回退全局。
    """
    token = _login(client)
    h = _auth_headers(token)

    wid = _pick_warehouse_id(client, token)
    _clear_warehouse_bindings(client, token, wid)

    # 为 provider A 创建可算 scheme，并绑定到仓库
    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_a = int(pdata[0]["id"])

    ids_a = _create_scheme_bundle_for_provider(client, token, provider_a, name_suffix="A")
    _bind_provider_to_warehouse(client, token, wid, provider_a)

    rr = client.post(
        "/shipping-quote/recommend",
        headers=h,
        json={
            "warehouse_id": wid,
            "provider_ids": [],
            "dest": {"province": "河北省", "city": "廊坊市", "district": "固安县"},
            "real_weight_kg": 1.0,
            "flags": [],
            "max_results": 10,
        },
    )
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert body["ok"] is True
    quotes = body["quotes"]
    assert quotes, "expected non-empty quotes when warehouse has bound provider with valid scheme"
    assert all(int(q["provider_id"]) == provider_a for q in quotes)
    assert body["recommended_scheme_id"] is not None
    # 至少包含我们创建的 scheme（可能存在同 provider 多 scheme，取最便宜的有效方案）
    assert any(int(q["scheme_id"]) == ids_a["scheme_id"] for q in quotes)


def test_shipping_quote_recommend_provider_ids_override_warehouse_phase2(client: TestClient) -> None:
    """
    Phase 2 兼容性合同测试：
    - 显式 provider_ids 优先级高于 warehouse_id（保持旧行为兼容）
    """
    token = _login(client)
    h = _auth_headers(token)

    wid = _pick_warehouse_id(client, token)
    _clear_warehouse_bindings(client, token, wid)

    # provider A: 绑定到仓库（让仓库候选集里只有 A）
    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_a = int(pdata[0]["id"])
    _create_scheme_bundle_for_provider(client, token, provider_a, name_suffix="A2")
    _bind_provider_to_warehouse(client, token, wid, provider_a)

    # provider B: 不绑定到仓库，但为其创建可算 scheme
    provider_b = _ensure_second_provider(client, token)
    ids_b = _create_scheme_bundle_for_provider(client, token, provider_b, name_suffix="B")
    # 不绑定 B 到仓库

    rr = client.post(
        "/shipping-quote/recommend",
        headers=h,
        json={
            "warehouse_id": wid,
            "provider_ids": [provider_b],
            "dest": {"province": "河北省", "city": "廊坊市", "district": "固安县"},
            "real_weight_kg": 1.0,
            "flags": [],
            "max_results": 10,
        },
    )
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert body["ok"] is True
    quotes = body["quotes"]
    assert quotes, "expected non-empty quotes when provider_ids explicitly provided with valid scheme"
    assert all(int(q["provider_id"]) == provider_b for q in quotes)
    assert any(int(q["scheme_id"]) == ids_b["scheme_id"] for q in quotes)
