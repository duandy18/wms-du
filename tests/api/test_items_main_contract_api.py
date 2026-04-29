# tests/api/test_items_main_contract_api.py
from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _sku(prefix: str = "UT-SKU") -> str:
    return f"{prefix}-{uuid4().hex[:8].upper()}"


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
        "sku": _sku(),
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "spec": "SPEC-A",
        "brand_id": 1,
        "category_id": 1,
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
async def test_items_create_requires_manual_sku(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    payload = {
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "spec": "SPEC-A",
        "brand_id": 1,
        "category_id": 1,
        "enabled": True,
        "supplier_id": 1,
        "lot_source_policy": "SUPPLIER_ONLY",
        "expiry_policy": "NONE",
        "derivation_allowed": True,
        "uom_governance_enabled": False,
    }

    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_items_create_accepts_128_char_manual_sku(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)
    sku = "S" + ("A" * 127)

    data = await _create_item(
        client,
        headers,
        sku=sku,
        expiry_policy="NONE",
        shelf_life_value=None,
        shelf_life_unit=None,
    )

    assert data["sku"] == sku


@pytest.mark.asyncio
async def test_items_create_persists_manual_sku_and_normalizes_uppercase(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)
    sku = _sku("manual-sku")

    data = await _create_item(
        client,
        headers,
        sku=sku.lower(),
        expiry_policy="NONE",
        shelf_life_value=None,
        shelf_life_unit=None,
    )

    assert data["sku"] == sku.upper()


@pytest.mark.asyncio
async def test_items_create_rejects_duplicate_manual_sku(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)
    sku = _sku("DUP-SKU")

    first = await _create_item(
        client,
        headers,
        sku=sku,
        expiry_policy="NONE",
        shelf_life_value=None,
        shelf_life_unit=None,
    )
    assert first["sku"] == sku

    payload = {
        "sku": sku,
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "spec": "SPEC-B",
        "brand_id": 2,
        "category_id": 2,
        "enabled": True,
        "supplier_id": 1,
        "lot_source_policy": "SUPPLIER_ONLY",
        "expiry_policy": "NONE",
        "derivation_allowed": True,
        "uom_governance_enabled": False,
    }

    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_items_create_rejects_barcode_field(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    payload = {
        "sku": _sku(),
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "barcode": "6900000000012",
    }
    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_items_create_rejects_has_shelf_life_field(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    payload = {
        "sku": _sku(),
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "has_shelf_life": True,
    }
    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_items_create_rejects_weight_kg_field(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    payload = {
        "sku": _sku(),
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
        "sku": _sku(),
        "name": f"UT-ITEM-{uuid4().hex[:8]}",
        "expiry_policy": "REQUIRED",
        "shelf_life_value": 0,
        "shelf_life_unit": "DAY",
    }
    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_items_create_auto_bootstraps_base_item_uom(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    created = await _create_item(client, headers)
    item_id = int(created["id"])

    row = (
        await session.execute(
            text(
                """
                SELECT
                  uom,
                  ratio_to_base,
                  display_name,
                  is_base,
                  is_purchase_default,
                  is_inbound_default,
                  is_outbound_default
                FROM item_uoms
                WHERE item_id = :item_id
                  AND is_base = true
                ORDER BY id ASC
                LIMIT 1
                """
            ),
            {"item_id": item_id},
        )
    ).mappings().first()

    assert row is not None, {"msg": "new item should auto-create base item_uom", "item_id": item_id}
    assert str(row["uom"]) == "PCS"
    assert int(row["ratio_to_base"]) == 1
    assert str(row["display_name"] or "").strip() == "PCS"
    assert bool(row["is_base"]) is True
    assert bool(row["is_purchase_default"]) is True
    assert bool(row["is_inbound_default"]) is True
    assert bool(row["is_outbound_default"]) is True

    base_count = await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM item_uoms
            WHERE item_id = :item_id
              AND is_base = true
            """
        ),
        {"item_id": item_id},
    )
    assert int(base_count.scalar_one()) == 1


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
