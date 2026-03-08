# tests/api/test_shipping_pricing_modules_api.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.api._helpers_shipping_quote import (
    auth_headers,
    bind_provider_to_warehouse,
    login,
    pick_warehouse_id,
    require_env,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    require_env()
    return TestClient(app)


def _create_scheme(client: TestClient, token: str):
    h = auth_headers(token)

    wid = pick_warehouse_id(client, token)

    pr = client.get("/shipping-providers", headers=h)
    provider_id = int(pr.json()["data"][0]["id"])

    bind_provider_to_warehouse(client, token, wid, provider_id)

    r = client.post(
        f"/shipping-providers/{provider_id}/pricing-schemes",
        headers=h,
        json={
            "warehouse_id": wid,
            "name": "TEST-SCHEME",
            "currency": "CNY",
            "default_pricing_mode": "linear_total",
            "billable_weight_strategy": "actual_only",
            "rounding_mode": "ceil",
            "rounding_step_kg": 1.0,
        },
    )

    return r.json()["data"]["id"]


def _build_module(client, h, scheme_id, module_code):

    ranges = [{"min_kg": 0, "max_kg": None}]

    r = client.put(
        f"/pricing-schemes/{scheme_id}/modules/{module_code}/ranges",
        headers=h,
        json={"ranges": ranges},
    )
    assert r.status_code == 200

    range_id = r.json()["ranges"][0]["id"]

    groups = [
        {
            "name": f"group-{module_code}",
            "provinces": [{"province_name": "北京市"}],
        }
    ]

    r = client.put(
        f"/pricing-schemes/{scheme_id}/modules/{module_code}/groups",
        headers=h,
        json={"groups": groups},
    )
    assert r.status_code == 200

    group_id = r.json()["groups"][0]["id"]

    cells = [
        {
            "group_id": group_id,
            "module_range_id": range_id,
            "pricing_mode": "flat",
            "flat_amount": 3.0,
        }
    ]

    r = client.put(
        f"/pricing-schemes/{scheme_id}/modules/{module_code}/matrix-cells",
        headers=h,
        json={"cells": cells},
    )
    assert r.status_code == 200


def test_ranges_groups_cells_replace_and_publish(client: TestClient):

    token = login(client)
    h = auth_headers(token)

    scheme_id = _create_scheme(client, token)

    _build_module(client, h, scheme_id, "standard")
    _build_module(client, h, scheme_id, "other")

    r = client.post(
        f"/pricing-schemes/{scheme_id}/publish",
        headers=h,
    )

    assert r.status_code == 200
    assert r.json()["data"]["status"] == "active"


def test_publish_blocked_when_cells_missing(client: TestClient):

    token = login(client)
    h = auth_headers(token)

    scheme_id = _create_scheme(client, token)

    r = client.put(
        f"/pricing-schemes/{scheme_id}/modules/standard/ranges",
        headers=h,
        json={"ranges": [{"min_kg": 0, "max_kg": None}]},
    )

    r = client.put(
        f"/pricing-schemes/{scheme_id}/modules/standard/groups",
        headers=h,
        json={
            "groups": [
                {
                    "name": "test",
                    "provinces": [{"province_name": "北京市"}],
                }
            ]
        },
    )

    r = client.post(
        f"/pricing-schemes/{scheme_id}/publish",
        headers=h,
    )

    assert r.status_code == 422
