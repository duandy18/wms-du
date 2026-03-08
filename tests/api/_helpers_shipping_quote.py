# tests/api/_helpers_shipping_quote.py
from __future__ import annotations

import os
from typing import Dict, List

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


def _put_module_groups(
    client: TestClient,
    token: str,
    *,
    scheme_id: int,
    module_code: str,
    groups: List[dict],
) -> List[dict]:
    h = auth_headers(token)

    r = client.put(
        f"/pricing-schemes/{scheme_id}/modules/{module_code}/groups",
        headers=h,
        json={"groups": groups},
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["ok"] is True
    return body["groups"]


def _put_module_ranges(
    client: TestClient,
    token: str,
    *,
    scheme_id: int,
    module_code: str,
    ranges: List[dict],
) -> List[dict]:
    h = auth_headers(token)

    r = client.put(
        f"/pricing-schemes/{scheme_id}/modules/{module_code}/ranges",
        headers=h,
        json={"ranges": ranges},
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["ok"] is True
    return body["ranges"]


def _put_module_matrix_cells(
    client: TestClient,
    token: str,
    *,
    scheme_id: int,
    module_code: str,
    cells: List[dict],
) -> List[dict]:
    h = auth_headers(token)

    r = client.put(
        f"/pricing-schemes/{scheme_id}/modules/{module_code}/matrix-cells",
        headers=h,
        json={"cells": cells},
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["ok"] is True
    return body["cells"]


def _publish_scheme(client: TestClient, token: str, *, scheme_id: int) -> None:
    h = auth_headers(token)

    r = client.post(f"/pricing-schemes/{scheme_id}/publish", headers=h)
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "active"


def _create_level3_bundle_via_api(
    client: TestClient,
    token: str,
    *,
    scheme_id: int,
    group_name: str,
    provinces: List[str],
    matrix_rows: List[dict],
) -> int:
    """
    通过新三阶段接口构造最小 Level-3 bundle：

      scheme
        -> standard module
        -> module_groups
        -> module_ranges
        -> matrix_cells
        -> other module（最小闭环，满足 publish）
    """

    # ------------------------------
    # standard module
    # ------------------------------
    standard_groups_out = _put_module_groups(
        client,
        token,
        scheme_id=scheme_id,
        module_code="standard",
        groups=[
            {
                "name": group_name,
                "sort_order": 0,
                "active": True,
                "provinces": [{"province_name": p} for p in provinces],
            }
        ],
    )
    assert len(standard_groups_out) == 1, standard_groups_out
    standard_group_id = int(standard_groups_out[0]["id"])

    standard_ranges_out = _put_module_ranges(
        client,
        token,
        scheme_id=scheme_id,
        module_code="standard",
        ranges=[
            {
                "min_kg": row["min_kg"],
                "max_kg": row["max_kg"],
                "sort_order": idx,
            }
            for idx, row in enumerate(matrix_rows)
        ],
    )
    assert len(standard_ranges_out) == len(matrix_rows), standard_ranges_out

    standard_cells_payload: List[dict] = []
    for idx, row in enumerate(matrix_rows):
        standard_cells_payload.append(
            {
                "group_id": standard_group_id,
                "module_range_id": int(standard_ranges_out[idx]["id"]),
                "pricing_mode": str(row["pricing_mode"]),
                "flat_amount": row.get("flat_amount"),
                "base_amount": row.get("base_amount"),
                "rate_per_kg": row.get("rate_per_kg"),
                "base_kg": row.get("base_kg"),
                "active": bool(row.get("active", True)),
            }
        )

    standard_cells_out = _put_module_matrix_cells(
        client,
        token,
        scheme_id=scheme_id,
        module_code="standard",
        cells=standard_cells_payload,
    )
    assert len(standard_cells_out) == len(matrix_rows), standard_cells_out

    # ------------------------------
    # other module（必须补齐，否则 publish 会被拦）
    # ------------------------------
    other_ranges_out = _put_module_ranges(
        client,
        token,
        scheme_id=scheme_id,
        module_code="other",
        ranges=[
            {
                "min_kg": 0,
                "max_kg": None,
                "sort_order": 0,
            }
        ],
    )
    assert len(other_ranges_out) == 1, other_ranges_out
    other_range_id = int(other_ranges_out[0]["id"])

    other_groups_out = _put_module_groups(
        client,
        token,
        scheme_id=scheme_id,
        module_code="other",
        groups=[
            {
                "name": "OTHER",
                "sort_order": 0,
                "active": True,
                "provinces": [{"province_name": "其他"}],
            }
        ],
    )
    assert len(other_groups_out) == 1, other_groups_out
    other_group_id = int(other_groups_out[0]["id"])

    other_cells_out = _put_module_matrix_cells(
        client,
        token,
        scheme_id=scheme_id,
        module_code="other",
        cells=[
            {
                "group_id": other_group_id,
                "module_range_id": other_range_id,
                "pricing_mode": "manual_quote",
                "flat_amount": None,
                "base_amount": None,
                "rate_per_kg": None,
                "base_kg": None,
                "active": True,
            }
        ],
    )
    assert len(other_cells_out) == 1, other_cells_out

    return standard_group_id


def create_scheme_bundle(client: TestClient, token: str) -> Dict[str, int]:
    """
    创建一套最小可算的 Level-3 单轨 scheme：

    provider
      -> scheme(warehouse scoped)
      -> standard module
      -> destination_group
      -> destination_group_members
      -> module_ranges
      -> pricing_matrix_cells
      -> other module（最小闭环）
      -> surcharge
      -> publish(active)
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

    group_id = _create_level3_bundle_via_api(
        client,
        token,
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

    _publish_scheme(client, token, scheme_id=scheme_id)

    return {
        "provider_id": provider_id,
        "scheme_id": scheme_id,
        "group_id": group_id,
    }


def create_scheme_bundle_for_provider(
    client: TestClient,
    token: str,
    provider_id: int,
    *,
    name_suffix: str,
) -> Dict[str, int]:
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

    group_id = _create_level3_bundle_via_api(
        client,
        token,
        scheme_id=scheme_id,
        group_name=group_name,
        provinces=provinces,
        matrix_rows=matrix_rows,
    )

    _publish_scheme(client, token, scheme_id=scheme_id)

    return {
        "provider_id": provider_id,
        "scheme_id": scheme_id,
        "group_id": group_id,
    }
