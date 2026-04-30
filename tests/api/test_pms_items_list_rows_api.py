# tests/api/test_pms_items_list_rows_api.py
from __future__ import annotations

from typing import Any

import httpx
import pytest


async def _login_admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _assert_item_list_row_contract(row: dict[str, Any]) -> None:
    required = {
        "item_id",
        "sku",
        "name",
        "spec",
        "enabled",
        "brand",
        "category",
        "supplier_name",
        "primary_barcode",
        "base_uom",
        "base_net_weight_kg",
        "purchase_uom",
        "purchase_ratio_to_base",
        "lot_source_policy",
        "expiry_policy",
        "shelf_life_value",
        "shelf_life_unit",
        "uom_count",
        "barcode_count",
        "sku_code_count",
        "attribute_count",
        "updated_at",
    }
    assert required <= set(row.keys()), row

    assert isinstance(row["item_id"], int), row
    assert isinstance(row["sku"], str) and row["sku"].strip(), row
    assert isinstance(row["name"], str) and row["name"].strip(), row
    assert isinstance(row["enabled"], bool), row

    for key in ("uom_count", "barcode_count", "sku_code_count", "attribute_count"):
        assert isinstance(row[key], int), row
        assert row[key] >= 0, row

    assert "brand_id" not in row, row
    assert "category_id" not in row, row
    assert "supplier_id" not in row, row
    assert "base_uom_id" not in row, row
    assert "purchase_uom_id" not in row, row


@pytest.mark.asyncio
async def test_item_list_rows_returns_owner_summary_contract(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/items/list-rows?limit=20", headers=headers)
    assert r.status_code == 200, r.text

    rows = r.json()
    assert isinstance(rows, list), rows
    assert rows, "base seed should expose at least one item list row"

    _assert_item_list_row_contract(rows[0])


@pytest.mark.asyncio
async def test_item_list_rows_supports_enabled_filter(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/items/list-rows?enabled=true&limit=50", headers=headers)
    assert r.status_code == 200, r.text

    rows = r.json()
    assert isinstance(rows, list), rows
    assert rows, "base seed should expose enabled item rows"
    assert all(row["enabled"] is True for row in rows), rows


@pytest.mark.asyncio
async def test_item_list_rows_supports_q_filter(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/items/list-rows?limit=1", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows, rows

    sku = str(rows[0]["sku"])
    rq = await client.get(f"/items/list-rows?q={sku}&limit=20", headers=headers)
    assert rq.status_code == 200, rq.text

    q_rows = rq.json()
    assert any(int(row["item_id"]) == int(rows[0]["item_id"]) for row in q_rows), q_rows
