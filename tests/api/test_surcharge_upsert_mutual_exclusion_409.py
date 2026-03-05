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
    # ref looks like "#/components/schemas/XXX"
    assert ref.startswith("#/"), ref
    cur: Any = spec
    for part in ref[2:].split("/"):
        cur = cur[part]
    assert isinstance(cur, dict), cur
    return cur


def _build_min_payload_from_schema(spec: Dict[str, Any], schema: Dict[str, Any], *, seed: str) -> Dict[str, Any]:
    """
    用 openapi schema 的 required 字段构造一个最小 payload，避免手写字段猜错。
    只处理 object 顶层 required（足够覆盖你们这类 create 接口）。
    """
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
            # unknown / oneOf / anyOf: best-effort empty object
            out[k] = {}

    return out


async def _ensure_scheme_id(async_client, headers: Dict[str, str]) -> int:
    """
    目标：拿到一个可用 scheme_id。
    优先复用已有 provider + scheme；不存在则通过 openapi 生成最小 payload 创建。
    """
    # 1) 先找 provider
    pr = await async_client.get("/shipping-providers", headers=headers)
    assert pr.status_code == 200, pr.text
    providers = pr.json()
    provider_id: Optional[int] = None
    if isinstance(providers, list) and providers:
        pid = providers[0].get("id")
        if isinstance(pid, int) and pid > 0:
            provider_id = pid

    # 2) 没 provider 就创建
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
        # 常见字段名兜底：name/code
        payload.setdefault("name", f"UT_PROVIDER_{seed}")
        payload.setdefault("code", f"UTP{seed}".upper())

        cr = await async_client.post("/shipping-providers", headers=headers, json=payload)
        assert cr.status_code in (200, 201), cr.text
        data = cr.json()
        # 兼容 {id:..} / {data:{id:..}}
        pid = data.get("id") if isinstance(data, dict) else None
        if not isinstance(pid, int):
            pid = (data.get("data", {}) or {}).get("id") if isinstance(data, dict) else None
        assert isinstance(pid, int) and pid > 0, data
        provider_id = pid

    # 3) 找 scheme
    sr = await async_client.get(f"/shipping-providers/{provider_id}/pricing-schemes", headers=headers)
    assert sr.status_code == 200, sr.text
    schemes = sr.json()
    scheme_id: Optional[int] = None
    if isinstance(schemes, list) and schemes:
        sid = schemes[0].get("id")
        if isinstance(sid, int) and sid > 0:
            scheme_id = sid
    if scheme_id is not None:
        return scheme_id

    # 4) 没 scheme 就创建
    o = await async_client.get("/openapi.json")
    assert o.status_code == 200, o.text
    spec = o.json()

    post_schema = (
        spec.get("paths", {})
        .get("/shipping-providers/{provider_id}/pricing-schemes", {})
        .get("post", {})
        .get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )

    seed = uuid4().hex[:8]
    payload = _build_min_payload_from_schema(spec, post_schema, seed=seed)
    payload.setdefault("name", f"UT_SCHEME_{seed}")
    payload.setdefault("currency", "CNY")

    cr = await async_client.post(f"/shipping-providers/{provider_id}/pricing-schemes", headers=headers, json=payload)
    assert cr.status_code in (200, 201), cr.text
    data = cr.json()
    sid = (data.get("data", {}) or {}).get("id") if isinstance(data, dict) else None
    if not isinstance(sid, int):
        sid = data.get("id") if isinstance(data, dict) else None
    assert isinstance(sid, int) and sid > 0, data
    return sid


@pytest.mark.anyio
async def test_surcharge_upsert_city_then_province_conflict_409(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    scheme_id = await _ensure_scheme_id(client, h)

    prov = "UT_PROV_GUANGDONG"
    city = "UT_CITY_SHENZHEN"

    r1 = await client.post(
        f"/pricing-schemes/{scheme_id}/surcharges:upsert",
        headers=h,
        json={"scope": "city", "province": prov, "city": city, "amount": 2.0, "active": True},
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.post(
        f"/pricing-schemes/{scheme_id}/surcharges:upsert",
        headers=h,
        json={"scope": "province", "province": prov, "amount": 1.0, "active": True},
    )
    assert r2.status_code == 409, r2.text
    assert "conflict" in r2.text.lower()


@pytest.mark.anyio
async def test_surcharge_upsert_province_then_city_conflict_409(client) -> None:
    token = await _login(client)
    h = _auth_headers(token)
    scheme_id = await _ensure_scheme_id(client, h)

    prov = "UT_PROV_GUANGDONG_2"
    city = "UT_CITY_GUANGZHOU_2"

    r1 = await client.post(
        f"/pricing-schemes/{scheme_id}/surcharges:upsert",
        headers=h,
        json={"scope": "province", "province": prov, "amount": 1.5, "active": True},
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.post(
        f"/pricing-schemes/{scheme_id}/surcharges:upsert",
        headers=h,
        json={"scope": "city", "province": prov, "city": city, "amount": 2.5, "active": True},
    )
    assert r2.status_code == 409, r2.text
    assert "conflict" in r2.text.lower()
