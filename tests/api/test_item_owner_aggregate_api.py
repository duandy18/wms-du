# tests/api/test_item_owner_aggregate_api.py
from __future__ import annotations

from typing import Any, Dict

import httpx
import pytest


async def _login_admin_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_payload() -> Dict[str, Any]:
    return {
        "item": {
            "name": "UT-AGG-ITEM",
            "spec": "500g",
            "brand": "BRAND-A",
            "category": "CATEGORY-A",
            "enabled": True,
            "supplier_id": 1,
            "lot_source_policy": "SUPPLIER_ONLY",
            "expiry_policy": "NONE",
            "derivation_allowed": True,
            "uom_governance_enabled": True,
            "shelf_life_value": None,
            "shelf_life_unit": None,
        },
        "uoms": [
            {
                "id": None,
                "uom_key": "BASE",
                "uom": "PCS",
                "ratio_to_base": 1,
                "display_name": "PCS",
                "net_weight_kg": None,
                "is_base": True,
                "is_purchase_default": False,
                "is_inbound_default": True,
                "is_outbound_default": True,
            },
            {
                "id": None,
                "uom_key": "PURCHASE",
                "uom": "BOX",
                "ratio_to_base": 12,
                "display_name": "箱",
                "net_weight_kg": None,
                "is_base": False,
                "is_purchase_default": True,
                "is_inbound_default": False,
                "is_outbound_default": False,
            },
        ],
        "barcodes": [
            {
                "id": None,
                "barcode": "UT-AGG-ITEM-BC-BASE",
                "symbology": "CUSTOM",
                "active": True,
                "is_primary": True,
                "bind_uom_key": "BASE",
            },
            {
                "id": None,
                "barcode": "UT-AGG-ITEM-BC-BOX",
                "symbology": "CUSTOM",
                "active": True,
                "is_primary": False,
                "bind_uom_key": "PURCHASE",
            },
        ],
    }


@pytest.mark.asyncio
async def test_create_and_get_item_aggregate(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    payload = _create_payload()

    r = await client.post("/items/aggregate", json=payload, headers=headers)
    assert r.status_code == 201, r.text

    body = r.json()
    assert isinstance(body, dict)

    item = body["item"]
    uoms = body["uoms"]
    barcodes = body["barcodes"]

    assert item["name"] == "UT-AGG-ITEM"
    assert item["brand"] == "BRAND-A"
    assert item["category"] == "CATEGORY-A"
    assert item["supplier_id"] == 1
    assert item["expiry_policy"] == "NONE"
    assert item["lot_source_policy"] == "SUPPLIER_ONLY"

    assert isinstance(uoms, list)
    assert len(uoms) == 2

    base = next(x for x in uoms if x["is_base"] is True)
    purchase = next(x for x in uoms if x["is_purchase_default"] is True)

    assert base["uom"] == "PCS"
    assert base["ratio_to_base"] == 1
    assert purchase["uom"] == "BOX"
    assert purchase["ratio_to_base"] == 12

    assert isinstance(barcodes, list)
    assert len(barcodes) == 2
    primary = next(x for x in barcodes if x["is_primary"] is True)
    assert primary["barcode"] == "UT-AGG-ITEM-BC-BASE"
    assert int(primary["item_uom_id"]) == int(base["id"])

    item_id = int(item["id"])

    r_get = await client.get(f"/items/{item_id}/aggregate", headers=headers)
    assert r_get.status_code == 200, r_get.text
    got = r_get.json()

    assert got["item"]["id"] == item_id
    assert len(got["uoms"]) == 2
    assert len(got["barcodes"]) == 2



@pytest.mark.asyncio
async def test_replace_item_aggregate_can_drop_purchase_uom_and_purchase_barcode(
    client: httpx.AsyncClient,
) -> None:
    headers = await _login_admin_headers(client)

    create_payload = _create_payload()
    r_create = await client.post("/items/aggregate", json=create_payload, headers=headers)
    assert r_create.status_code == 201, r_create.text
    created = r_create.json()

    item_id = int(created["item"]["id"])
    base_uom = next(x for x in created["uoms"] if x["is_base"] is True)
    primary_barcode = next(x for x in created["barcodes"] if x["is_primary"] is True)

    replace_payload = {
        "item": {
            "name": "UT-AGG-ITEM-V2",
            "spec": "750g",
            "brand": "BRAND-B",
            "category": "CATEGORY-B",
            "enabled": True,
            "supplier_id": 1,
            "lot_source_policy": "SUPPLIER_ONLY",
            "expiry_policy": "NONE",
            "derivation_allowed": False,
            "uom_governance_enabled": True,
            "shelf_life_value": None,
            "shelf_life_unit": None,
        },
        "uoms": [
            {
                "id": int(base_uom["id"]),
                "uom_key": "BASE",
                "uom": "PCS",
                "ratio_to_base": 1,
                "display_name": "PCS",
                "net_weight_kg": None,
                "is_base": True,
                "is_purchase_default": True,
                "is_inbound_default": True,
                "is_outbound_default": True,
            }
        ],
        "barcodes": [
            {
                "id": int(primary_barcode["id"]),
                "barcode": "UT-AGG-ITEM-BC-BASE-V2",
                "symbology": "CUSTOM",
                "active": True,
                "is_primary": True,
                "bind_uom_key": "BASE",
            }
        ],
    }

    r_put = await client.put(f"/items/{item_id}/aggregate", json=replace_payload, headers=headers)
    assert r_put.status_code == 200, r_put.text

    body = r_put.json()
    assert body["item"]["name"] == "UT-AGG-ITEM-V2"
    assert body["item"]["brand"] == "BRAND-B"
    assert body["item"]["category"] == "CATEGORY-B"
    assert body["item"]["derivation_allowed"] is False

    assert len(body["uoms"]) == 1
    only_uom = body["uoms"][0]
    assert only_uom["is_base"] is True
    assert only_uom["is_purchase_default"] is True

    assert len(body["barcodes"]) == 1
    only_barcode = body["barcodes"][0]
    assert only_barcode["barcode"] == "UT-AGG-ITEM-BC-BASE-V2"
    assert only_barcode["is_primary"] is True
    assert int(only_barcode["item_uom_id"]) == int(only_uom["id"])

    r_get = await client.get(f"/items/{item_id}/aggregate", headers=headers)
    assert r_get.status_code == 200, r_get.text
    got = r_get.json()

    assert got["item"]["name"] == "UT-AGG-ITEM-V2"
    assert len(got["uoms"]) == 1
    assert len(got["barcodes"]) == 1
