# tests/api/_helpers_pricing_matrix.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest
import httpx


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _pick_id_any(obj: Any) -> Optional[int]:
    """
    从常见响应形态里提取 id：
    - {"id": ...} / {"scheme_id": ...} / {"provider_id": ...} / {"shipping_provider_id": ...} / {"zone_id": ...} / {"template_id": ...} / {"segment_template_id": ...}
    - {"data": {...}} / {"result": {...}} / {"provider": {...}} / {"scheme": {...}} / {"zone": {...}} / {"template": {...}}
    """
    if not isinstance(obj, dict):
        return None

    for k in ("id", "scheme_id", "provider_id", "shipping_provider_id", "zone_id", "template_id", "segment_template_id"):
        if k in obj and obj[k] is not None:
            try:
                return int(obj[k])
            except Exception:
                pass

    for nest in ("data", "result", "provider", "scheme", "zone", "template"):
        got = _pick_id_any(obj.get(nest))
        if got is not None:
            return got

    return None


async def login_admin_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _openapi_schema_ref(client: httpx.AsyncClient, path: str, method: str) -> Optional[str]:
    o = await client.get("/openapi.json")
    assert o.status_code == 200, o.text
    spec = o.json()
    p = spec.get("paths", {}).get(path, {}).get(method.lower(), {})
    schema = (
        p.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )
    if isinstance(schema, dict) and "$ref" in schema:
        return str(schema["$ref"])
    return None


async def _openapi_components(client: httpx.AsyncClient) -> Dict[str, Any]:
    o = await client.get("/openapi.json")
    assert o.status_code == 200, o.text
    spec = o.json()
    return spec.get("components", {}).get("schemas", {}) or {}


def _deref(components: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    ref = schema.get("$ref")
    if not ref:
        return schema
    name = ref.split("/")[-1]
    target = components.get(name)
    return target if isinstance(target, dict) else schema


def _synth_value(components: Dict[str, Any], schema: Dict[str, Any], field_name: str) -> Any:
    schema = _deref(components, schema)

    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    for k in ("oneOf", "anyOf", "allOf"):
        if k in schema and isinstance(schema[k], list) and schema[k]:
            return _synth_value(components, schema[k][0], field_name)

    t = schema.get("type")
    if t == "string":
        min_len = int(schema.get("minLength") or 1)
        base = f"UT_{field_name}".upper()
        if len(base) < min_len:
            base += "X" * (min_len - len(base))
        return base[: max(min_len, 64)]
    if t == "boolean":
        return True
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "array":
        return []
    if t == "object":
        return {}
    return "UT"


def _build_payload_from_ref(components: Dict[str, Any], ref: str) -> Dict[str, Any]:
    name = ref.split("/")[-1]
    sch = components.get(name)
    if not isinstance(sch, dict):
        raise KeyError(name)

    props: Dict[str, Any] = sch.get("properties") or {}
    required: List[str] = sch.get("required") or []

    payload: Dict[str, Any] = {}
    for f in required:
        fs = props.get(f, {})
        payload[f] = _synth_value(components, fs, f)

    if "name" in props and "name" not in payload:
        payload["name"] = "UT_PROVIDER"
    if "code" in props and "code" not in payload:
        payload["code"] = "UT_PROVIDER"
    if "active" in props and "active" not in payload:
        payload["active"] = True

    return payload


async def ensure_provider_id(client: httpx.AsyncClient, headers: Dict[str, str]) -> int:
    r = await client.get("/shipping-providers", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    if isinstance(data, list) and data:
        item = data[0]
        if isinstance(item, dict):
            got = _pick_id_any(item)
            if got is not None:
                return got
        pytest.fail(f"Unexpected /shipping-providers list item shape: {item}")

    ref = await _openapi_schema_ref(client, "/shipping-providers", "post")
    if not ref:
        pytest.skip("No providers in test DB and OpenAPI lacks POST /shipping-providers request schema.")

    components = await _openapi_components(client)
    payload = _build_payload_from_ref(components, ref)
    payload_code = _norm(payload.get("code"))
    payload_name = _norm(payload.get("name"))

    cr = await client.post("/shipping-providers", headers=headers, json=payload)
    assert cr.status_code in (200, 201), cr.text

    try:
        created = cr.json()
    except Exception:
        created = None

    pid = _pick_id_any(created)
    if pid is not None:
        return pid

    rr = await client.get("/shipping-providers", headers=headers)
    assert rr.status_code == 200, rr.text
    providers = rr.json()
    assert isinstance(providers, list) and providers

    if payload_code:
        for p in providers:
            if isinstance(p, dict) and _norm(p.get("code")) == payload_code:
                got = _pick_id_any(p)
                if got is not None:
                    return got

    if payload_name:
        for p in providers:
            if isinstance(p, dict) and _norm(p.get("name")) == payload_name:
                got = _pick_id_any(p)
                if got is not None:
                    return got

    got = _pick_id_any(providers[-1]) if isinstance(providers[-1], dict) else None
    if got is not None:
        return got
    pytest.fail(f"Cannot resolve provider_id from /shipping-providers list: last={providers[-1]}")


async def ensure_scheme_id(client: httpx.AsyncClient, headers: Dict[str, str], provider_id: int, name: str) -> int:
    r = await client.post(
        f"/shipping-providers/{provider_id}/pricing-schemes",
        headers=headers,
        json={"name": name},
    )
    assert r.status_code in (200, 201), r.text

    try:
        data = r.json()
    except Exception:
        data = None

    sid = _pick_id_any(data)
    if sid is not None:
        return sid

    rr = await client.get(f"/shipping-providers/{provider_id}/pricing-schemes", headers=headers)
    assert rr.status_code == 200, rr.text
    items = rr.json()
    if isinstance(items, dict):
        if isinstance(items.get("items"), list):
            items = items["items"]
        elif isinstance(items.get("data"), list):
            items = items["data"]
    assert isinstance(items, list) and items

    wanted = _norm(name)
    for s in items:
        if isinstance(s, dict) and _norm(s.get("name")) == wanted:
            sid = _pick_id_any(s)
            if sid is not None:
                return sid

    sid = _pick_id_any(items[-1]) if isinstance(items[-1], dict) else None
    if sid is not None:
        return sid
    pytest.fail(f"Cannot resolve scheme_id from list item: {items[-1]}")


async def create_segment_template(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    scheme_id: int,
    name: str,
    segments: List[Tuple[str, Optional[str]]],
) -> int:
    """
    Pricing smoke 只需要 template_id 用于分组，不强制验证模板段生命周期。
    因此这里仅负责创建并返回 template_id，不做 publish/activate/items 持久化的强制动作。
    """
    items = [{"min_kg": mn, "max_kg": mx} for (mn, mx) in segments]
    payload_candidates = [
        {"name": name, "items": items},
        {"name": name, "segments": items},
    ]

    last_resp: Optional[httpx.Response] = None
    for payload in payload_candidates:
        r = await client.post(f"/pricing-schemes/{scheme_id}/segment-templates", headers=headers, json=payload)
        last_resp = r
        if r.status_code in (200, 201):
            data = r.json()
            tid = _pick_id_any(data)
            if tid is not None:
                return tid
            # 兼容旧形态
            raw = data.get("id") or data.get("template_id") or data.get("segment_template_id")
            if raw is not None:
                return int(raw)
            pytest.fail(f"Cannot resolve template_id from create response: {data}")

    pytest.skip(
        f"Cannot create segment template (last_status={getattr(last_resp,'status_code',None)} body={getattr(last_resp,'text','')})."
    )


async def create_zone(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    scheme_id: int,
    *,
    name: str,
    provinces: List[str],
    active: bool = True,
    segment_template_id: Optional[int] = None,
) -> int:
    """
    ✅ 新合同：Zone 必须绑定 segment_template_id
    为了让测试造数简单：当 segment_template_id 缺省时，这里自动创建一个最小模板并绑定。
    同时：由于此 helper 需要 provinces，因此统一走 zones-atomic 入口。
    """
    if segment_template_id is None:
        # 最小行结构即可：不要求生命周期，不要求 items 长度 > 1
        segment_template_id = await create_segment_template(
            client,
            headers,
            scheme_id,
            name=f"{name}-TPL",
            segments=[("0.000", "1.000")],
        )

    payload: Dict[str, Any] = {
        "name": name,
        "active": active,
        "provinces": provinces,
        "segment_template_id": int(segment_template_id),
    }

    r = await client.post(f"/pricing-schemes/{scheme_id}/zones-atomic", headers=headers, json=payload)
    assert r.status_code in (200, 201), r.text

    data = r.json()
    zid = _pick_id_any(data)
    if zid is not None:
        return zid
    if isinstance(data, dict) and "id" in data:
        return int(data["id"])
    pytest.fail(f"Cannot resolve zone_id from create zone response: {data}")


async def create_zones(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    scheme_id: int,
    zones: List[Dict[str, Any]],
) -> List[int]:
    ids: List[int] = []
    for z in zones:
        ids.append(
            await create_zone(
                client,
                headers,
                scheme_id,
                name=str(z["name"]),
                provinces=list(z.get("provinces") or []),
                active=bool(z.get("active", True)),
                segment_template_id=(int(z["segment_template_id"]) if z.get("segment_template_id") is not None else None),
            )
        )
    return ids


async def create_bracket_flat(
    client: httpx.AsyncClient, headers: Dict[str, str], zone_id: int, min_kg: str, max_kg: Optional[str]
) -> None:
    payload = {
        "min_kg": min_kg,
        "max_kg": max_kg,
        "pricing_mode": "flat",
        "flat_amount": "15.00",
        "active": True,
    }
    r = await client.post(f"/zones/{zone_id}/brackets", headers=headers, json=payload)
    assert r.status_code in (200, 201), r.text


async def create_bracket_step_over(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    zone_id: int,
    min_kg: str,
    max_kg: Optional[str],
) -> None:
    payload = {
        "min_kg": min_kg,
        "max_kg": max_kg,
        "pricing_mode": "step_over",
        "base_kg": "1.000",
        "base_amount": "15.00",
        "rate_per_kg": "10.0000",
        "active": True,
    }
    r = await client.post(f"/zones/{zone_id}/brackets", headers=headers, json=payload)
    assert r.status_code in (200, 201), r.text
