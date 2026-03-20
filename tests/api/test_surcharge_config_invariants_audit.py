# tests/api/test_surcharge_config_invariants_audit.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(async_client) -> str:
    r = await async_client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    data = r.json()
    token = data.get("access_token")
    assert isinstance(token, str) and token, data
    return token


def _resolve_ref(spec: Dict[str, Any], ref: str) -> Dict[str, Any]:
    assert ref.startswith("#/"), ref
    cur: Any = spec
    for part in ref[2:].split("/"):
        cur = cur[part]
    assert isinstance(cur, dict), cur
    return cur


def _build_min_payload_from_schema(spec: Dict[str, Any], schema: Dict[str, Any], *, seed: str) -> Dict[str, Any]:
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])

    if schema.get("type") != "object":
        return {}

    props = schema.get("properties") or {}
    required = schema.get("required") or []
    out: Dict[str, Any] = {}

    for k in required:
        p = props.get(k) or {}
        if "$ref" in p:
            p = _resolve_ref(spec, p["$ref"])

        t = p.get("type")
        if t == "string":
            out[k] = f"UT_{k}_{seed}"
        elif t == "boolean":
            out[k] = True
        elif t == "integer":
            out[k] = 1
        elif t == "number":
            out[k] = 1.0
        elif t == "array":
            out[k] = []
        elif t == "object":
            out[k] = {}
        else:
            out[k] = {}

    return out


async def _pick_warehouse_id(async_client, headers: Dict[str, str]) -> int:
    r = await async_client.get("/warehouses", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    rows = data.get("data") if isinstance(data, dict) else data
    assert isinstance(rows, list) and rows, f"no warehouses: {data}"
    first = rows[0]
    assert isinstance(first, dict) and "id" in first, f"unexpected warehouse item shape: {first}"
    return int(first["id"])


async def _bind_provider_to_warehouse(
    async_client,
    headers: Dict[str, str],
    warehouse_id: int,
    provider_id: int,
) -> None:
    r = await async_client.post(
        f"/tms/pricing/warehouses/{int(warehouse_id)}/bindings",
        headers=headers,
        json={
            "shipping_provider_id": int(provider_id),
            "active": True,
            "priority": 0,
            "pickup_cutoff_time": "18:00",
            "remark": "surcharge audit bind",
        },
    )
    assert r.status_code in (200, 201, 409), r.text
    if r.status_code == 409:
        pr = await async_client.patch(
            f"/tms/pricing/warehouses/{int(warehouse_id)}/bindings/{int(provider_id)}",
            headers=headers,
            json={"active": True, "priority": 0},
        )
        assert pr.status_code == 200, pr.text


async def _ensure_template_id(async_client, headers: Dict[str, str]) -> int:
    wid = await _pick_warehouse_id(async_client, headers)

    pr = await async_client.get("/shipping-providers", headers=headers)
    assert pr.status_code == 200, pr.text
    providers_body = pr.json()
    providers = providers_body.get("data") if isinstance(providers_body, dict) else providers_body

    provider_id: Optional[int] = None
    if isinstance(providers, list) and providers:
        pid = providers[0].get("id") if isinstance(providers[0], dict) else None
        if isinstance(pid, int) and pid > 0:
            provider_id = pid

    if provider_id is None:
        o = await async_client.get("/openapi.json")
        assert o.status_code == 200, o.text
        spec: Dict[str, Any] = o.json()

        post_schema = (
            spec.get("paths", {})
            .get("/shipping-providers", {})
            .get("post", {})
            .get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        seed = uuid4().hex[:8]
        payload = _build_min_payload_from_schema(spec, post_schema, seed=seed)
        payload.setdefault("name", f"UT_PROVIDER_{seed}")
        payload.setdefault("code", f"UTP{seed}".upper())
        payload.setdefault("warehouse_id", int(wid))

        cr = await async_client.post("/shipping-providers", headers=headers, json=payload)
        assert cr.status_code in (200, 201), cr.text
        data = cr.json()
        pid = data.get("id") if isinstance(data, dict) else None
        if not isinstance(pid, int):
            pid = (data.get("data", {}) or {}).get("id") if isinstance(data, dict) else None
        assert isinstance(pid, int) and pid > 0, data
        provider_id = pid

    await _bind_provider_to_warehouse(async_client, headers, int(wid), int(provider_id))

    tr = await async_client.get(
        f"/tms/pricing/shipping-providers/{int(provider_id)}/templates",
        headers=headers,
    )
    assert tr.status_code == 200, tr.text
    templates_body = tr.json()
    templates = templates_body.get("data") if isinstance(templates_body, dict) else templates_body

    template_id: Optional[int] = None
    if isinstance(templates, list) and templates:
        for item in templates:
            if isinstance(item, dict):
                tid = item.get("id")
                status = str(item.get("status") or "").strip().lower()
                if isinstance(tid, int) and tid > 0 and status == "draft":
                    template_id = tid
                    break
        if template_id is None:
            for item in templates:
                if isinstance(item, dict):
                    tid = item.get("id")
                    if isinstance(tid, int) and tid > 0:
                        template_id = tid
                        break
    if template_id is not None:
        return template_id

    o = await async_client.get("/openapi.json")
    assert o.status_code == 200, o.text
    spec = o.json()

    post_schema = (
        spec.get("paths", {})
        .get("/tms/pricing/templates", {})
        .get("post", {})
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )

    seed = uuid4().hex[:8]
    payload = _build_min_payload_from_schema(spec, post_schema, seed=seed)
    payload.setdefault("shipping_provider_id", int(provider_id))
    payload.setdefault("name", f"UT_TEMPLATE_{seed}")
    payload.setdefault("currency", "CNY")
    payload.setdefault("default_pricing_mode", "linear_total")
    payload.setdefault("billable_weight_strategy", "actual_only")
    payload.setdefault("rounding_mode", "none")

    cr = await async_client.post("/tms/pricing/templates", headers=headers, json=payload)
    assert cr.status_code in (200, 201), cr.text
    data = cr.json()
    tid = (data.get("data", {}) or {}).get("id") if isinstance(data, dict) else None
    if not isinstance(tid, int):
        tid = data.get("id") if isinstance(data, dict) else None
    assert isinstance(tid, int) and tid > 0, data
    return tid


async def _create_config(
    async_client,
    headers: Dict[str, str],
    *,
    template_id: int,
    province_code: str,
    province_name: str,
    province_mode: str,
    fixed_amount: float,
    cities: List[Dict[str, object]],
) -> tuple[int, dict]:
    r = await async_client.post(
        f"/tms/pricing/templates/{template_id}/surcharge-configs",
        headers=headers,
        json={
            "province_code": province_code,
            "province_name": province_name,
            "province_mode": province_mode,
            "fixed_amount": fixed_amount,
            "active": True,
            "cities": cities,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert isinstance(body, dict), body
    return int(body["id"]), body


@pytest.mark.anyio
async def test_surcharge_config_invariant_province_mode_rejects_non_empty_cities(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    r = await client.post(
        f"/tms/pricing/templates/{template_id}/surcharge-configs",
        headers=h,
        json={
            "province_code": "110000",
            "province_name": "北京市",
            "province_mode": "province",
            "fixed_amount": 1.5,
            "active": True,
            "cities": [
                {
                    "city_code": "110100",
                    "city_name": "北京市",
                    "fixed_amount": 2.0,
                    "active": True,
                }
            ],
        },
    )
    assert r.status_code == 422, r.text
    assert "cities" in r.text


@pytest.mark.anyio
async def test_surcharge_config_invariant_cities_mode_allows_empty_container(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    r = await client.post(
        f"/tms/pricing/templates/{template_id}/surcharge-configs",
        headers=h,
        json={
            "province_code": "120000",
            "province_name": "天津市",
            "province_mode": "cities",
            "fixed_amount": 0,
            "active": True,
            "cities": [],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["province_mode"] == "cities"
    assert body["province_code"] == "120000"
    assert body["province_name"] == "天津市"
    assert float(body["fixed_amount"]) == 0.0
    assert body["cities"] == []


@pytest.mark.anyio
async def test_surcharge_config_invariant_cities_mode_requires_zero_fixed_amount(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    r = await client.post(
        f"/tms/pricing/templates/{template_id}/surcharge-configs",
        headers=h,
        json={
            "province_code": "310000",
            "province_name": "上海市",
            "province_mode": "cities",
            "fixed_amount": 9.9,
            "active": True,
            "cities": [
                {
                    "city_code": "310100",
                    "city_name": "上海市",
                    "fixed_amount": 2.0,
                    "active": True,
                }
            ],
        },
    )
    assert r.status_code == 422, r.text
    assert "fixed_amount" in r.text


@pytest.mark.anyio
async def test_surcharge_config_patch_invariant_switch_to_province_requires_empty_cities(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    config_id, _ = await _create_config(
        client,
        h,
        template_id=template_id,
        province_code="440000",
        province_name="广东省",
        province_mode="cities",
        fixed_amount=0,
        cities=[
            {
                "city_code": "440300",
                "city_name": "深圳市",
                "fixed_amount": 2.0,
                "active": True,
            }
        ],
    )

    r = await client.patch(
        f"/tms/pricing/surcharge-configs/{config_id}",
        headers=h,
        json={
            "province_mode": "province",
            "fixed_amount": 1.0,
            "cities": [
                {
                    "city_code": "440300",
                    "city_name": "深圳市",
                    "fixed_amount": 2.0,
                    "active": True,
                }
            ],
        },
    )
    assert r.status_code == 422, r.text
    assert "cities" in r.text


@pytest.mark.anyio
async def test_surcharge_config_patch_invariant_switch_to_cities_requires_zero_fixed_amount_but_allows_empty_container(
    client,
) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    config_id, _ = await _create_config(
        client,
        h,
        template_id=template_id,
        province_code="450000",
        province_name="广西壮族自治区",
        province_mode="province",
        fixed_amount=1.5,
        cities=[],
    )

    r1 = await client.patch(
        f"/tms/pricing/surcharge-configs/{config_id}",
        headers=h,
        json={
            "province_mode": "cities",
            "fixed_amount": 3.5,
            "cities": [],
        },
    )
    assert r1.status_code == 422, r1.text
    assert "fixed_amount" in r1.text

    r2 = await client.patch(
        f"/tms/pricing/surcharge-configs/{config_id}",
        headers=h,
        json={
            "province_mode": "cities",
            "fixed_amount": 0,
            "cities": [],
        },
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["id"] == config_id
    assert body["province_mode"] == "cities"
    assert float(body["fixed_amount"]) == 0.0
    assert body["cities"] == []


@pytest.mark.anyio
async def test_surcharge_config_city_container_route_allows_empty_container(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    r = await client.post(
        f"/tms/pricing/templates/{template_id}/surcharge-configs/city-container",
        headers=h,
        json={
            "province_code": "500000",
            "province_name": "重庆市",
            "active": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["province_code"] == "500000"
    assert body["province_name"] == "重庆市"
    assert body["province_mode"] == "cities"
    assert float(body["fixed_amount"]) == 0.0
    assert body["cities"] == []
