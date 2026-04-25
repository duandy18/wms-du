# tests/api/test_surcharge_upsert_mutual_exclusion_409.py
from __future__ import annotations

from typing import Any, Dict, Optional
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
        f"/shipping-assist/pricing/warehouses/{int(warehouse_id)}/bindings",
        headers=headers,
        json={
            "shipping_provider_id": int(provider_id),
            "active": True,
            "priority": 0,
            "pickup_cutoff_time": "18:00",
            "remark": "surcharge test bind",
        },
    )
    assert r.status_code in (200, 201, 409), r.text
    if r.status_code == 409:
        pr = await async_client.patch(
            f"/shipping-assist/pricing/warehouses/{int(warehouse_id)}/bindings/{int(provider_id)}",
            headers=headers,
            json={"active": True, "priority": 0},
        )
        assert pr.status_code == 200, pr.text


async def _ensure_template_id(async_client, headers: Dict[str, str]) -> int:
    wid = await _pick_warehouse_id(async_client, headers)

    pr = await async_client.get("/shipping-assist/pricing/providers", headers=headers)
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
            .get("/shipping-assist/pricing/providers", {})
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

        cr = await async_client.post("/shipping-assist/pricing/providers", headers=headers, json=payload)
        assert cr.status_code in (200, 201), cr.text
        data = cr.json()
        pid = data.get("id") if isinstance(data, dict) else None
        if not isinstance(pid, int):
            pid = (data.get("data", {}) or {}).get("id") if isinstance(data, dict) else None
        assert isinstance(pid, int) and pid > 0, data
        provider_id = pid

    await _bind_provider_to_warehouse(async_client, headers, int(wid), int(provider_id))

    tr = await async_client.get(
        f"/shipping-assist/pricing/providers/{int(provider_id)}/templates",
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
                validation_status = str(item.get("validation_status") or "").strip().lower()
                if (
                    isinstance(tid, int)
                    and tid > 0
                    and status == "draft"
                    and validation_status == "not_validated"
                ):
                    template_id = tid
                    break
    if template_id is not None:
        return template_id

    o = await async_client.get("/openapi.json")
    assert o.status_code == 200, o.text
    spec = o.json()

    post_schema = (
        spec.get("paths", {})
        .get("/shipping-assist/pricing/templates", {})
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

    cr = await async_client.post("/shipping-assist/pricing/templates", headers=headers, json=payload)
    assert cr.status_code in (200, 201), cr.text
    data = cr.json()
    tid = (data.get("data", {}) or {}).get("id") if isinstance(data, dict) else None
    if not isinstance(tid, int):
        tid = data.get("id") if isinstance(data, dict) else None
    assert isinstance(tid, int) and tid > 0, data
    return tid


async def _create_surcharge_config(
    async_client,
    headers: Dict[str, str],
    *,
    template_id: int,
    province_code: str,
    province_name: str,
    province_mode: str,
    fixed_amount: float,
    cities: list[dict[str, object]],
) -> dict:
    r = await async_client.post(
        f"/shipping-assist/pricing/templates/{template_id}/surcharge-configs",
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
    return body


@pytest.mark.anyio
async def test_surcharge_config_create_city_mode_then_patch_to_province_mode(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    province_code = "440000"
    province_name = "广东省"
    city_code = "440300"
    city_name = "深圳市"

    body1 = await _create_surcharge_config(
        client,
        h,
        template_id=template_id,
        province_code=province_code,
        province_name=province_name,
        province_mode="cities",
        fixed_amount=0,
        cities=[
            {
                "city_code": city_code,
                "city_name": city_name,
                "fixed_amount": 2.0,
                "active": True,
            }
        ],
    )
    assert body1["province_mode"] == "cities"
    assert body1["province_code"] == province_code
    assert body1["province_name"] == province_name
    assert float(body1["fixed_amount"]) == 0.0
    assert len(body1["cities"]) == 1
    assert body1["cities"][0]["city_code"] == city_code
    assert body1["cities"][0]["city_name"] == city_name
    assert float(body1["cities"][0]["fixed_amount"]) == 2.0

    config_id = int(body1["id"])

    r2 = await client.patch(
        f"/shipping-assist/pricing/surcharge-configs/{config_id}",
        headers=h,
        json={
            "province_code": province_code,
            "province_name": province_name,
            "province_mode": "province",
            "fixed_amount": 1.0,
            "active": True,
            "cities": [],
        },
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["id"] == config_id
    assert body2["province_mode"] == "province"
    assert body2["province_code"] == province_code
    assert body2["province_name"] == province_name
    assert float(body2["fixed_amount"]) == 1.0
    assert body2["cities"] == []


@pytest.mark.anyio
async def test_surcharge_config_create_province_mode_then_patch_to_cities_mode(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    province_code = "450000"
    province_name = "广西壮族自治区"
    city_code = "450100"
    city_name = "南宁市"

    body1 = await _create_surcharge_config(
        client,
        h,
        template_id=template_id,
        province_code=province_code,
        province_name=province_name,
        province_mode="province",
        fixed_amount=1.5,
        cities=[],
    )
    assert body1["province_mode"] == "province"
    assert body1["province_code"] == province_code
    assert body1["province_name"] == province_name
    assert float(body1["fixed_amount"]) == 1.5
    assert body1["cities"] == []

    config_id = int(body1["id"])

    r2 = await client.patch(
        f"/shipping-assist/pricing/surcharge-configs/{config_id}",
        headers=h,
        json={
            "province_code": province_code,
            "province_name": province_name,
            "province_mode": "cities",
            "fixed_amount": 0,
            "active": True,
            "cities": [
                {
                    "city_code": city_code,
                    "city_name": city_name,
                    "fixed_amount": 2.5,
                    "active": True,
                }
            ],
        },
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["id"] == config_id
    assert body2["province_mode"] == "cities"
    assert body2["province_code"] == province_code
    assert body2["province_name"] == province_name
    assert float(body2["fixed_amount"]) == 0.0
    assert len(body2["cities"]) == 1
    assert body2["cities"][0]["city_code"] == city_code
    assert body2["cities"][0]["city_name"] == city_name
    assert float(body2["cities"][0]["fixed_amount"]) == 2.5


@pytest.mark.anyio
async def test_surcharge_config_batch_province_create_skips_existing_and_payload_duplicates(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    existing = await _create_surcharge_config(
        client,
        h,
        template_id=template_id,
        province_code="110000",
        province_name="北京市",
        province_mode="province",
        fixed_amount=1.0,
        cities=[],
    )
    assert existing["province_code"] == "110000"

    r = await client.post(
        f"/shipping-assist/pricing/templates/{template_id}/surcharge-configs/batch-province",
        headers=h,
        json={
            "items": [
                {
                    "province_code": "110000",
                    "province_name": "北京市",
                    "fixed_amount": 1.1,
                    "active": True,
                },
                {
                    "province_code": "120000",
                    "province_name": "天津市",
                    "fixed_amount": 2.2,
                    "active": True,
                },
                {
                    "province_code": "120000",
                    "province_name": "天津市",
                    "fixed_amount": 2.2,
                    "active": True,
                },
                {
                    "province_code": "130000",
                    "province_name": "河北省",
                    "fixed_amount": 3.3,
                    "active": False,
                },
            ]
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()

    created = body["created"]
    skipped = body["skipped"]

    assert len(created) == 2, body
    assert [row["province_code"] for row in created] == ["120000", "130000"]
    assert all(row["province_mode"] == "province" for row in created)
    assert float(created[0]["fixed_amount"]) == 2.2
    assert created[0]["active"] is True
    assert created[0]["cities"] == []
    assert float(created[1]["fixed_amount"]) == 3.3
    assert created[1]["active"] is False
    assert created[1]["cities"] == []

    assert len(skipped) == 2, body
    assert skipped[0] == {
        "province_code": "110000",
        "province_name": "北京市",
        "reason": "already_exists",
    }
    assert skipped[1] == {
        "province_code": "120000",
        "province_name": "天津市",
        "reason": "duplicate_in_payload",
    }


@pytest.mark.anyio
async def test_surcharge_config_city_container_create_then_patch_add_cities(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    r1 = await client.post(
        f"/shipping-assist/pricing/templates/{template_id}/surcharge-configs/city-container",
        headers=h,
        json={
            "province_code": "320000",
            "province_name": "江苏省",
            "active": True,
        },
    )
    assert r1.status_code == 201, r1.text
    body1 = r1.json()
    assert body1["province_mode"] == "cities"
    assert body1["province_code"] == "320000"
    assert body1["province_name"] == "江苏省"
    assert float(body1["fixed_amount"]) == 0.0
    assert body1["cities"] == []

    config_id = int(body1["id"])

    r2 = await client.patch(
        f"/shipping-assist/pricing/surcharge-configs/{config_id}",
        headers=h,
        json={
            "cities": [
                {
                    "city_code": "320100",
                    "city_name": "南京市",
                    "fixed_amount": 2.0,
                    "active": True,
                },
                {
                    "city_code": "320500",
                    "city_name": "苏州市",
                    "fixed_amount": 3.0,
                    "active": True,
                },
            ]
        },
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["id"] == config_id
    assert body2["province_mode"] == "cities"
    assert len(body2["cities"]) == 2
    assert [row["city_code"] for row in body2["cities"]] == ["320100", "320500"]


@pytest.mark.anyio
async def test_surcharge_config_city_container_create_rejects_duplicate_province(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    template_id = await _ensure_template_id(client, h)

    r1 = await client.post(
        f"/shipping-assist/pricing/templates/{template_id}/surcharge-configs/city-container",
        headers=h,
        json={
            "province_code": "330000",
            "province_name": "浙江省",
            "active": True,
        },
    )
    assert r1.status_code == 201, r1.text

    r2 = await client.post(
        f"/shipping-assist/pricing/templates/{template_id}/surcharge-configs/city-container",
        headers=h,
        json={
            "province_code": "330000",
            "province_name": "浙江省",
            "active": True,
        },
    )
    assert r2.status_code == 409, r2.text
    assert "already exists" in r2.text
