# tests/api/_helpers_shipping_quote.py
from __future__ import annotations

import os
from typing import Dict, Optional

from fastapi.testclient import TestClient


def require_env() -> None:
    if not (os.getenv("WMS_DATABASE_URL") or os.getenv("WMS_TEST_DATABASE_URL")):
        raise RuntimeError("WMS_TEST_DATABASE_URL / WMS_DATABASE_URL 未设置（Makefile 应该已注入）")


def login(client: TestClient, username: str = "admin", password: str = "admin123") -> str:
    r = client.post("/users/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token
    return token


def auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def pick_warehouse_id(client: TestClient, token: str) -> int:
    r = client.get("/warehouses", headers=auth_headers(token))
    assert r.status_code == 200, r.text
    rows = r.json()["data"]
    assert rows, "no warehouses"
    return int(rows[0]["id"])


def clear_warehouse_bindings(client: TestClient, token: str, warehouse_id: int) -> None:
    h = auth_headers(token)
    r = client.get(f"/warehouses/{warehouse_id}/shipping-providers", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()["data"] or []
    for it in data:
        pid = int(it["shipping_provider_id"])
        dr = client.delete(f"/warehouses/{warehouse_id}/shipping-providers/{pid}", headers=h)
        assert dr.status_code in (200, 404), dr.text


def bind_provider_to_warehouse(client: TestClient, token: str, warehouse_id: int, provider_id: int) -> None:
    h = auth_headers(token)
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
    assert r.status_code in (201, 409), r.text
    if r.status_code == 409:
        pr = client.patch(
            f"/warehouses/{warehouse_id}/shipping-providers/{provider_id}",
            headers=h,
            json={"active": True, "priority": 0},
        )
        assert pr.status_code == 200, pr.text


def bind_scheme_to_warehouse(client: TestClient, token: str, scheme_id: int, warehouse_id: int) -> None:
    """
    Phase 3/4 合同（测试用）：
    - 单条绑定：POST /pricing-schemes/{scheme_id}/warehouses/bind
    """
    h = auth_headers(token)
    r = client.post(
        f"/pricing-schemes/{int(scheme_id)}/warehouses/bind",
        headers=h,
        json={"warehouse_id": int(warehouse_id), "active": True},
    )
    assert r.status_code in (200, 201), r.text


def unbind_scheme_from_warehouse(client: TestClient, token: str, scheme_id: int, warehouse_id: int) -> None:
    h = auth_headers(token)
    r = client.delete(
        f"/pricing-schemes/{int(scheme_id)}/warehouses/{int(warehouse_id)}",
        headers=h,
    )
    assert r.status_code in (200, 204, 404), r.text


def assert_scheme_bound_to_warehouse(client: TestClient, token: str, scheme_id: int, warehouse_id: int) -> None:
    h = auth_headers(token)
    r = client.get(f"/pricing-schemes/{int(scheme_id)}/warehouses", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()["data"] or []
    assert any(int(x["warehouse_id"]) == int(warehouse_id) and bool(x["active"]) is True for x in data), r.text


def ensure_second_provider(client: TestClient, token: str) -> int:
    """
    Phase 6 刚性契约：
    - POST /shipping-providers 创建必须带 warehouse_id
    """
    h = auth_headers(token)
    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"] or []
    if len(pdata) >= 2:
        return int(pdata[1]["id"])

    wid = pick_warehouse_id(client, token)

    cr = client.post(
        "/shipping-providers",
        headers=h,
        json={
            "name": "TEST-PROVIDER-2",
            "code": "TP2",
            "active": True,
            "priority": 100,
            "warehouse_id": int(wid),
            "pricing_model": None,
            "region_rules": None,
        },
    )
    assert cr.status_code == 201, cr.text
    return int(cr.json()["data"]["id"])


def _pick_template_id(data: dict) -> int:
    # 兼容常见响应形态
    for k in ("id", "template_id", "segment_template_id"):
        if k in data and data[k] is not None:
            return int(data[k])
    if "data" in data and isinstance(data["data"], dict):
        return _pick_template_id(data["data"])
    raise AssertionError(f"cannot resolve template_id from response: {data}")


def _create_min_template(client: TestClient, token: str, scheme_id: int, name: str) -> int:
    """
    Zone 新合同：必须绑定 segment_template_id。
    这里创建一个最小模板（带最小 items），不依赖 publish/activate 生命周期。
    """
    h = auth_headers(token)

    # 优先 items
    r = client.post(
        f"/pricing-schemes/{scheme_id}/segment-templates",
        headers=h,
        json={
            "name": name,
            "items": [{"min_kg": "0.000", "max_kg": "1.000"}, {"min_kg": "1.000", "max_kg": None}],
        },
    )
    if r.status_code not in (200, 201):
        # fallback segments
        r = client.post(
            f"/pricing-schemes/{scheme_id}/segment-templates",
            headers=h,
            json={
                "name": name,
                "segments": [{"min_kg": "0.000", "max_kg": "1.000"}, {"min_kg": "1.000", "max_kg": None}],
            },
        )

    assert r.status_code in (200, 201), r.text
    return _pick_template_id(r.json())


def create_scheme_bundle(client: TestClient, token: str) -> Dict[str, int]:
    """
    创建一套最小可算的 scheme：
    provider -> scheme -> segment_template -> zone_atomic -> brackets + surcharge
    """
    h = auth_headers(token)

    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_id = int(pdata[0]["id"])

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

    # ✅ 新合同：Zone 必绑模板 —— 先创建一个最小模板
    tpl_id = _create_min_template(client, token, scheme_id, name="TEST-TPL-BASE")

    zr = client.post(
        f"/pricing-schemes/{scheme_id}/zones-atomic",
        headers=h,
        json={
            "name": "北京市、天津市、河北省",
            "priority": 100,
            "active": True,
            "provinces": ["北京市", "天津市", "河北省"],
            "segment_template_id": int(tpl_id),
        },
    )
    assert zr.status_code == 201, zr.text
    zone_id = int(zr.json()["id"])

    for b in [
        {"min_kg": 0.0, "max_kg": 1.0, "pricing_mode": "flat", "flat_amount": 2.5, "active": True},
        {"min_kg": 1.01, "max_kg": 2.0, "pricing_mode": "flat", "flat_amount": 3.8, "active": True},
        {"min_kg": 2.01, "max_kg": 3.0, "pricing_mode": "flat", "flat_amount": 4.8, "active": True},
        {"min_kg": 3.01, "max_kg": 30.0, "pricing_mode": "linear_total", "base_amount": 3.0, "rate_per_kg": 1.2, "active": True},
        {"min_kg": 30.01, "max_kg": None, "pricing_mode": "linear_total", "base_amount": 3.0, "rate_per_kg": 1.5, "active": True},
    ]:
        br = client.post(f"/zones/{zone_id}/brackets", headers=h, json=b)
        assert br.status_code == 201, br.text

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

    return {"provider_id": provider_id, "scheme_id": scheme_id, "zone_id": zone_id, "template_id": tpl_id}


def create_scheme_bundle_for_provider(client: TestClient, token: str, provider_id: int, *, name_suffix: str) -> Dict[str, int]:
    """
    为指定 provider 创建一套最小可算的 scheme（用于推荐/候选集测试）。
    """
    h = auth_headers(token)

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

    # ✅ 新合同：Zone 必绑模板
    tpl_id = _create_min_template(client, token, scheme_id, name=f"TEST-TPL-{name_suffix}")

    zr = client.post(
        f"/pricing-schemes/{scheme_id}/zones-atomic",
        headers=h,
        json={
            "name": f"河北省-TEST-{name_suffix}",
            "priority": 100,
            "active": True,
            "provinces": ["河北省"],
            "segment_template_id": int(tpl_id),
        },
    )
    assert zr.status_code == 201, zr.text
    zone_id = int(zr.json()["id"])

    br = client.post(
        f"/zones/{zone_id}/brackets",
        headers=h,
        json={
            "min_kg": 0.0,
            "max_kg": None,
            "pricing_mode": "linear_total",
            "base_amount": 8.0,
            "rate_per_kg": 2.0,
            "active": True,
        },
    )
    assert br.status_code == 201, br.text

    return {"provider_id": provider_id, "scheme_id": scheme_id, "zone_id": zone_id, "template_id": tpl_id}
