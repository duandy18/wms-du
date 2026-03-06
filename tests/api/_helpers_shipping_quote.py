# tests/api/_helpers_shipping_quote.py
from __future__ import annotations

import os
from decimal import Decimal
from typing import Dict, Iterable

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.shipping_provider_destination_group import ShippingProviderDestinationGroup
from app.models.shipping_provider_destination_group_member import (
    ShippingProviderDestinationGroupMember,
)
from app.models.shipping_provider_pricing_matrix import ShippingProviderPricingMatrix


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
    for k in ("id", "template_id", "segment_template_id"):
        if k in data and data[k] is not None:
            return int(data[k])
    if "data" in data and isinstance(data["data"], dict):
        return _pick_template_id(data["data"])
    raise AssertionError(f"cannot resolve template_id from response: {data}")


def _publish_template(client: TestClient, token: str, template_id: int) -> None:
    h = auth_headers(token)
    r = client.post(f"/segment-templates/{int(template_id)}:publish", headers=h, json={})
    assert r.status_code in (200, 201), r.text


def _put_min_items(client: TestClient, token: str, template_id: int) -> None:
    h = auth_headers(token)
    r = client.put(
        f"/segment-templates/{int(template_id)}/items",
        headers=h,
        json={
            "items": [
                {"ord": 0, "min_kg": "0.000", "max_kg": "1.000", "active": True},
                {"ord": 1, "min_kg": "1.000", "max_kg": None, "active": True},
            ]
        },
    )
    assert r.status_code in (200, 201), r.text


def _create_min_template(client: TestClient, token: str, scheme_id: int, name: str) -> int:
    """
    Zone 新合同：必须绑定 segment_template_id（且模板必须 published）。
    这里创建一个最小模板（create -> put items -> publish）。
    """
    h = auth_headers(token)

    r = client.post(
        f"/pricing-schemes/{scheme_id}/segment-templates",
        headers=h,
        json={"name": name},
    )
    assert r.status_code in (200, 201), r.text
    tid = _pick_template_id(r.json())

    _put_min_items(client, token, tid)
    _publish_template(client, token, tid)
    return tid


def _insert_level3_destination_group(
    *,
    scheme_id: int,
    name: str,
) -> int:
    db = SessionLocal()
    try:
        row = ShippingProviderDestinationGroup(
            scheme_id=int(scheme_id),
            name=str(name),
            active=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)
    finally:
        db.close()


def _replace_level3_group_provinces(
    *,
    group_id: int,
    provinces: Iterable[str],
) -> None:
    db = SessionLocal()
    try:
        db.query(ShippingProviderDestinationGroupMember).filter(
            ShippingProviderDestinationGroupMember.group_id == int(group_id)
        ).delete(synchronize_session=False)

        rows = [
            ShippingProviderDestinationGroupMember(
                group_id=int(group_id),
                scope="province",
                province_name=str(p),
            )
            for p in provinces
        ]
        db.add_all(rows)
        db.commit()
    finally:
        db.close()


def _insert_level3_pricing_matrix_row(
    *,
    group_id: int,
    min_kg: float,
    max_kg: float | None,
    pricing_mode: str,
    flat_amount: float | None = None,
    base_amount: float | None = None,
    rate_per_kg: float | None = None,
    base_kg: float | None = None,
    active: bool = True,
) -> None:
    db = SessionLocal()
    try:
        row = ShippingProviderPricingMatrix(
            group_id=int(group_id),
            min_kg=Decimal(str(min_kg)),
            max_kg=(None if max_kg is None else Decimal(str(max_kg))),
            pricing_mode=str(pricing_mode),
            flat_amount=(None if flat_amount is None else Decimal(str(flat_amount))),
            base_amount=(None if base_amount is None else Decimal(str(base_amount))),
            rate_per_kg=(None if rate_per_kg is None else Decimal(str(rate_per_kg))),
            base_kg=(None if base_kg is None else Decimal(str(base_kg))),
            active=bool(active),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()


def _mirror_legacy_bundle_to_level3(
    *,
    scheme_id: int,
    group_name: str,
    provinces: list[str],
    brackets: list[dict],
) -> int:
    """
    为当前 Phase C 测试构造 level3 镜像数据：
    legacy zone/members/brackets -> destination_group/members/matrix
    """
    group_id = _insert_level3_destination_group(
        scheme_id=scheme_id,
        name=group_name,
    )
    _replace_level3_group_provinces(
        group_id=group_id,
        provinces=provinces,
    )
    for b in brackets:
        _insert_level3_pricing_matrix_row(
            group_id=group_id,
            min_kg=float(b["min_kg"]),
            max_kg=(None if b["max_kg"] is None else float(b["max_kg"])),
            pricing_mode=str(b["pricing_mode"]),
            flat_amount=(None if b.get("flat_amount") is None else float(b["flat_amount"])),
            base_amount=(None if b.get("base_amount") is None else float(b["base_amount"])),
            rate_per_kg=(None if b.get("rate_per_kg") is None else float(b["rate_per_kg"])),
            base_kg=(None if b.get("base_kg") is None else float(b["base_kg"])),
            active=bool(b.get("active", True)),
        )
    return group_id


def create_scheme_bundle(client: TestClient, token: str) -> Dict[str, int]:
    """
    创建一套最小可算的 scheme：
    provider -> scheme(warehouse scoped) -> segment_template(published) -> zone_atomic -> brackets + surcharge
    同时镜像一套 level3 数据，用于 shadow compare 测试。
    """
    h = auth_headers(token)

    wid = pick_warehouse_id(client, token)

    pr = client.get("/shipping-providers", headers=h)
    assert pr.status_code == 200, pr.text
    pdata = pr.json()["data"]
    assert pdata, "no shipping providers"
    provider_id = int(pdata[0]["id"])

    bind_provider_to_warehouse(client, token, wid, provider_id)

    sr = client.post(
        f"/shipping-providers/{provider_id}/pricing-schemes",
        headers=h,
        json={
            "warehouse_id": int(wid),
            "name": "TEST-PRICING-SCHEME",
            "active": True,
            "priority": 100,
            "currency": "CNY",
            "billable_weight_rule": {"rounding": {"mode": "ceil", "step_kg": 1.0}},
        },
    )
    assert sr.status_code == 201, sr.text
    scheme_id = int(sr.json()["data"]["id"])

    tpl_id = _create_min_template(client, token, scheme_id, name="TEST-TPL-BASE")

    provinces = ["北京市", "天津市", "河北省"]
    zone_name = "北京市、天津市、河北省"

    zr = client.post(
        f"/pricing-schemes/{scheme_id}/zones-atomic",
        headers=h,
        json={
            "name": zone_name,
            "priority": 100,
            "active": True,
            "provinces": provinces,
            "segment_template_id": int(tpl_id),
        },
    )
    assert zr.status_code == 201, zr.text
    zone_id = int(zr.json()["id"])

    brackets = [
        {"min_kg": 0.0, "max_kg": 1.0, "pricing_mode": "flat", "flat_amount": 2.5, "active": True},
        {"min_kg": 1.01, "max_kg": 2.0, "pricing_mode": "flat", "flat_amount": 3.8, "active": True},
        {"min_kg": 2.01, "max_kg": 3.0, "pricing_mode": "flat", "flat_amount": 4.8, "active": True},
        {"min_kg": 3.01, "max_kg": 30.0, "pricing_mode": "linear_total", "base_amount": 3.0, "rate_per_kg": 1.2, "active": True},
        {"min_kg": 30.01, "max_kg": None, "pricing_mode": "linear_total", "base_amount": 3.0, "rate_per_kg": 1.5, "active": True},
    ]
    for b in brackets:
        br = client.post(f"/zones/{zone_id}/brackets", headers=h, json=b)
        assert br.status_code == 201, br.text

    group_id = _mirror_legacy_bundle_to_level3(
        scheme_id=scheme_id,
        group_name=zone_name,
        provinces=provinces,
        brackets=brackets,
    )

    sur = client.post(
        f"/pricing-schemes/{scheme_id}/surcharges",
        headers=h,
        json={
            "name": "目的地附加费-北京市",
            "priority": 100,
            "active": True,
            "stackable": True,
            "scope": "province",
            "province_name": "北京市",
            "fixed_amount": 1.5,
        },
    )
    assert sur.status_code == 201, sur.text

    return {
        "provider_id": provider_id,
        "scheme_id": scheme_id,
        "zone_id": zone_id,
        "template_id": tpl_id,
        "group_id": group_id,
    }


def create_scheme_bundle_for_provider(client: TestClient, token: str, provider_id: int, *, name_suffix: str) -> Dict[str, int]:
    """
    为指定 provider 创建一套最小可算的 scheme（用于推荐/候选集测试）。
    同时镜像一套 level3 数据，用于 shadow compare 测试。
    """
    h = auth_headers(token)
    wid = pick_warehouse_id(client, token)

    bind_provider_to_warehouse(client, token, wid, provider_id)

    sr = client.post(
        f"/shipping-providers/{provider_id}/pricing-schemes",
        headers=h,
        json={
            "warehouse_id": int(wid),
            "name": f"TEST-PRICING-SCHEME-{name_suffix}",
            "active": True,
            "priority": 100,
            "currency": "CNY",
            "billable_weight_rule": {"rounding": {"mode": "ceil", "step_kg": 1.0}},
        },
    )
    assert sr.status_code == 201, sr.text
    scheme_id = int(sr.json()["data"]["id"])

    tpl_id = _create_min_template(client, token, scheme_id, name=f"TEST-TPL-{name_suffix}")

    provinces = ["河北省"]
    zone_name = f"河北省-TEST-{name_suffix}"

    zr = client.post(
        f"/pricing-schemes/{scheme_id}/zones-atomic",
        headers=h,
        json={
            "name": zone_name,
            "priority": 100,
            "active": True,
            "provinces": provinces,
            "segment_template_id": int(tpl_id),
        },
    )
    assert zr.status_code == 201, zr.text
    zone_id = int(zr.json()["id"])

    brackets = [
        {
            "min_kg": 0.0,
            "max_kg": None,
            "pricing_mode": "linear_total",
            "base_amount": 8.0,
            "rate_per_kg": 2.0,
            "active": True,
        }
    ]
    br = client.post(
        f"/zones/{zone_id}/brackets",
        headers=h,
        json=brackets[0],
    )
    assert br.status_code == 201, br.text

    group_id = _mirror_legacy_bundle_to_level3(
        scheme_id=scheme_id,
        group_name=zone_name,
        provinces=provinces,
        brackets=brackets,
    )

    return {
        "provider_id": provider_id,
        "scheme_id": scheme_id,
        "zone_id": zone_id,
        "template_id": tpl_id,
        "group_id": group_id,
    }
