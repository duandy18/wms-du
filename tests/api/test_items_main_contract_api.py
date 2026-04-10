# tests/api/test_items_main_contract_api.py
from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

import httpx
import pytest


async def _login_admin_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_item(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    **overrides: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "spec": "SPEC-A",
        "brand": "BRAND-A",
        "category": "CATEGORY-A",
        "enabled": True,
        "supplier_id": 1,
        "lot_source_policy": "SUPPLIER_ONLY",
        "expiry_policy": "REQUIRED",
        "derivation_allowed": True,
        "uom_governance_enabled": False,
        "shelf_life_value": 12,
        "shelf_life_unit": "MONTH",
    }
    payload.update(overrides)
    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert isinstance(data, dict), data
    return data


@pytest.mark.asyncio
async def test_items_create_rejects_barcode_field(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    payload = {
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "barcode": "6900000000012",
    }
    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_items_create_rejects_has_shelf_life_field(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    payload = {
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "has_shelf_life": True,
    }
    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_items_create_rejects_weight_kg_field(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    payload = {
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "weight_kg": 1.25,
    }
    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_items_create_accepts_week_shelf_life_unit(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    data = await _create_item(
        client,
        headers,
        expiry_policy="REQUIRED",
        shelf_life_value=2,
        shelf_life_unit="WEEK",
    )

    assert data["expiry_policy"] == "REQUIRED"
    assert data["shelf_life_value"] == 2
    assert data["shelf_life_unit"] == "WEEK"


@pytest.mark.asyncio
async def test_items_create_rejects_zero_shelf_life_value(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    payload = {
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "expiry_policy": "REQUIRED",
        "shelf_life_value": 0,
        "shelf_life_unit": "DAY",
    }
    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_items_patch_explicit_null_clears_nullable_fields(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    created = await _create_item(
        client,
        headers,
        spec="SPEC-TO-CLEAR",
        supplier_id=1,
        expiry_policy="REQUIRED",
        shelf_life_value=9,
        shelf_life_unit="YEAR",
    )
    item_id = int(created["id"])

    patch_payload = {
        "spec": None,
        "supplier_id": None,
        "shelf_life_value": None,
        "shelf_life_unit": None,
    }
    r_patch = await client.patch(f"/items/{item_id}", json=patch_payload, headers=headers)
    assert r_patch.status_code == 200, r_patch.text
    patched = r_patch.json()

    assert patched["spec"] is None
    assert patched["supplier_id"] is None
    assert patched["shelf_life_value"] is None
    assert patched["shelf_life_unit"] is None

    r_get = await client.get(f"/items/{item_id}", headers=headers)
    assert r_get.status_code == 200, r_get.text
    fetched = r_get.json()

    assert fetched["spec"] is None
    assert fetched["supplier_id"] is None
    assert fetched["shelf_life_value"] is None
    assert fetched["shelf_life_unit"] is None


@pytest.mark.asyncio
async def test_items_patch_rejects_weight_kg_field(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    created = await _create_item(
        client,
        headers,
        expiry_policy="REQUIRED",
        shelf_life_value=30,
        shelf_life_unit="DAY",
    )
    item_id = int(created["id"])

    r_patch = await client.patch(
        f"/items/{item_id}",
        json={"weight_kg": None},
        headers=headers,
    )
    assert r_patch.status_code == 422, r_patch.text


@pytest.mark.asyncio
async def test_items_patch_sets_none_policy_and_clears_shelf_pair(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    created = await _create_item(
        client,
        headers,
        expiry_policy="REQUIRED",
        shelf_life_value=30,
        shelf_life_unit="DAY",
    )
    item_id = int(created["id"])

    r_patch = await client.patch(
        f"/items/{item_id}",
        json={"expiry_policy": "NONE"},
        headers=headers,
    )
    assert r_patch.status_code == 200, r_patch.text
    patched = r_patch.json()

    assert patched["expiry_policy"] == "NONE"
    assert patched["shelf_life_value"] is None
    assert patched["shelf_life_unit"] is None

    r_get = await client.get(f"/items/{item_id}", headers=headers)
    assert r_get.status_code == 200, r_get.text
    fetched = r_get.json()

    assert fetched["expiry_policy"] == "NONE"
    assert fetched["shelf_life_value"] is None
    assert fetched["shelf_life_unit"] is None
