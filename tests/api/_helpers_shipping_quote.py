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
from app.models.shipping_provider_pricing_scheme import ShippingProviderPricingScheme
from app.models.shipping_provider_pricing_scheme_module import ShippingProviderPricingSchemeModule
from app.models.shipping_provider_pricing_scheme_module_range import (
    ShippingProviderPricingSchemeModuleRange,
)


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


def _force_scheme_active(*, scheme_id: int) -> None:
    """
    当前正式合同：
    - 新建 scheme 默认 draft
    - 报价链路只接受 active
    测试 helper 需要把最小闭环 scheme 直接提升到 active。
    """
    db = SessionLocal()
    try:
        sch = db.get(ShippingProviderPricingScheme, int(scheme_id))
        assert sch is not None, f"scheme not found: scheme_id={scheme_id}"

        sch.status = "active"
        sch.archived_at = None
        db.commit()
    finally:
        db.close()


def _get_standard_module_id(*, scheme_id: int) -> int:
    db = SessionLocal()
    try:
        row = (
            db.query(ShippingProviderPricingSchemeModule)
            .filter(
                ShippingProviderPricingSchemeModule.scheme_id == int(scheme_id),
                ShippingProviderPricingSchemeModule.module_code == "standard",
            )
            .one_or_none()
        )
        assert row is not None, f"standard module not found for scheme_id={scheme_id}"
        return int(row.id)
    finally:
        db.close()


def _insert_level3_destination_group(
    *,
    scheme_id: int,
    module_id: int,
    name: str,
    sort_order: int = 0,
) -> int:
    db = SessionLocal()
    try:
        row = ShippingProviderDestinationGroup(
            scheme_id=int(scheme_id),
            module_id=int(module_id),
            name=str(name),
            sort_order=int(sort_order),
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
                province_name=str(p),
            )
            for p in provinces
        ]
        db.add_all(rows)
        db.commit()
    finally:
        db.close()


def _replace_standard_module_ranges_and_cells(
    *,
    module_id: int,
    group_id: int,
    matrix_rows: list[dict],
) -> None:
    db = SessionLocal()
    try:
        old_ranges = (
            db.query(ShippingProviderPricingSchemeModuleRange)
            .filter(ShippingProviderPricingSchemeModuleRange.module_id == int(module_id))
            .all()
        )
        old_range_ids = [int(x.id) for x in old_ranges]

        if old_range_ids:
            db.query(ShippingProviderPricingMatrix).filter(
                ShippingProviderPricingMatrix.module_range_id.in_(old_range_ids)
            ).delete(synchronize_session=False)

        db.query(ShippingProviderPricingSchemeModuleRange).filter(
            ShippingProviderPricingSchemeModuleRange.module_id == int(module_id)
        ).delete(synchronize_session=False)
        db.flush()

        for idx, row in enumerate(matrix_rows):
            r = ShippingProviderPricingSchemeModuleRange(
                module_id=int(module_id),
                min_kg=Decimal(str(row["min_kg"])),
                max_kg=(None if row["max_kg"] is None else Decimal(str(row["max_kg"]))),
                sort_order=idx,
            )
            db.add(r)
            db.flush()

            cell = ShippingProviderPricingMatrix(
                group_id=int(group_id),
                module_range_id=int(r.id),
                range_module_id=int(module_id),
                pricing_mode=str(row["pricing_mode"]),
                flat_amount=(None if row.get("flat_amount") is None else Decimal(str(row["flat_amount"]))),
                base_amount=(None if row.get("base_amount") is None else Decimal(str(row["base_amount"]))),
                rate_per_kg=(None if row.get("rate_per_kg") is None else Decimal(str(row["rate_per_kg"]))),
                base_kg=(None if row.get("base_kg") is None else Decimal(str(row["base_kg"]))),
                active=bool(row.get("active", True)),
            )
            db.add(cell)

        db.commit()
    finally:
        db.close()


def _create_level3_bundle(
    *,
    scheme_id: int,
    group_name: str,
    provinces: list[str],
    matrix_rows: list[dict],
) -> int:
    """
    D-2 单轨 helper（module-aware 版）：
    只构造当前 Level-3 主线数据：
      scheme
        -> standard module
        -> module_ranges
        -> destination_group
        -> destination_group_members
        -> pricing_matrix(cells)
    """
    module_id = _get_standard_module_id(scheme_id=scheme_id)

    group_id = _insert_level3_destination_group(
        scheme_id=scheme_id,
        module_id=module_id,
        name=group_name,
        sort_order=0,
    )
    _replace_level3_group_provinces(
        group_id=group_id,
        provinces=provinces,
    )
    _replace_standard_module_ranges_and_cells(
        module_id=module_id,
        group_id=group_id,
        matrix_rows=matrix_rows,
    )
    return group_id


def create_scheme_bundle(client: TestClient, token: str) -> Dict[str, int]:
    """
    创建一套最小可算的 Level-3 单轨 scheme：

    provider
      -> scheme(warehouse scoped)
      -> standard module
      -> destination_group
      -> destination_group_members
      -> module_ranges
      -> pricing_matrix
      -> surcharge
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
            "currency": "CNY",
            "default_pricing_mode": "linear_total",
            "billable_weight_strategy": "actual_only",
            "rounding_mode": "ceil",
            "rounding_step_kg": 1.0,
        },
    )
    assert sr.status_code == 201, sr.text
    scheme_id = int(sr.json()["data"]["id"])

    _force_scheme_active(scheme_id=scheme_id)

    provinces = ["北京市", "天津市", "河北省"]
    group_name = "北京市、天津市、河北省"

    matrix_rows = [
        {"min_kg": 0.0, "max_kg": 1.0, "pricing_mode": "flat", "flat_amount": 2.5, "active": True},
        {"min_kg": 1.0, "max_kg": 2.0, "pricing_mode": "flat", "flat_amount": 3.8, "active": True},
        {"min_kg": 2.0, "max_kg": 3.0, "pricing_mode": "flat", "flat_amount": 4.8, "active": True},
        {
            "min_kg": 3.0,
            "max_kg": 30.0,
            "pricing_mode": "linear_total",
            "base_amount": 3.0,
            "rate_per_kg": 1.2,
            "active": True,
        },
        {
            "min_kg": 30.0,
            "max_kg": None,
            "pricing_mode": "linear_total",
            "base_amount": 3.0,
            "rate_per_kg": 1.5,
            "active": True,
        },
    ]

    group_id = _create_level3_bundle(
        scheme_id=scheme_id,
        group_name=group_name,
        provinces=provinces,
        matrix_rows=matrix_rows,
    )

    sur = client.post(
        f"/pricing-schemes/{scheme_id}/surcharges",
        headers=h,
        json={
            "name": "目的地附加费-北京市",
            "active": True,
            "scope": "province",
            "province_name": "北京市",
            "fixed_amount": 1.5,
        },
    )
    assert sur.status_code == 201, sur.text

    return {
        "provider_id": provider_id,
        "scheme_id": scheme_id,
        "group_id": group_id,
    }


def create_scheme_bundle_for_provider(client: TestClient, token: str, provider_id: int, *, name_suffix: str) -> Dict[str, int]:
    """
    为指定 provider 创建一套最小可算的 Level-3 单轨 scheme（用于推荐/候选集测试）。
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
            "currency": "CNY",
            "default_pricing_mode": "linear_total",
            "billable_weight_strategy": "actual_only",
            "rounding_mode": "ceil",
            "rounding_step_kg": 1.0,
        },
    )
    assert sr.status_code == 201, sr.text
    scheme_id = int(sr.json()["data"]["id"])

    _force_scheme_active(scheme_id=scheme_id)

    provinces = ["河北省"]
    group_name = f"河北省-TEST-{name_suffix}"

    matrix_rows = [
        {
            "min_kg": 0.0,
            "max_kg": None,
            "pricing_mode": "linear_total",
            "base_amount": 8.0,
            "rate_per_kg": 2.0,
            "active": True,
        }
    ]

    group_id = _create_level3_bundle(
        scheme_id=scheme_id,
        group_name=group_name,
        provinces=provinces,
        matrix_rows=matrix_rows,
    )

    return {
        "provider_id": provider_id,
        "scheme_id": scheme_id,
        "group_id": group_id,
    }
