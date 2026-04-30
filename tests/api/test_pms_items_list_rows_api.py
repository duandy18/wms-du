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


def _assert_detail_contract(data: dict[str, Any]) -> None:
    assert set(data.keys()) == {"row", "uoms", "barcodes", "sku_codes", "attributes"}, data

    row = data["row"]
    assert isinstance(row, dict), data
    _assert_item_list_row_contract(row)

    for key in ("uoms", "barcodes", "sku_codes", "attributes"):
        assert isinstance(data[key], list), data

    for uom in data["uoms"]:
        assert {
            "id",
            "item_id",
            "uom",
            "display_name",
            "ratio_to_base",
            "net_weight_kg",
            "is_base",
            "is_purchase_default",
            "is_inbound_default",
            "is_outbound_default",
            "updated_at",
        } <= set(uom.keys()), uom
        assert int(uom["item_id"]) == int(row["item_id"]), uom
        assert isinstance(uom["uom"], str) and uom["uom"].strip(), uom
        assert isinstance(uom["ratio_to_base"], int) and uom["ratio_to_base"] >= 1, uom

    for barcode in data["barcodes"]:
        assert {
            "id",
            "item_id",
            "item_uom_id",
            "uom",
            "display_name",
            "barcode",
            "symbology",
            "active",
            "is_primary",
            "updated_at",
        } <= set(barcode.keys()), barcode
        assert int(barcode["item_id"]) == int(row["item_id"]), barcode
        assert isinstance(barcode["barcode"], str) and barcode["barcode"].strip(), barcode

    for code in data["sku_codes"]:
        assert {
            "id",
            "item_id",
            "code",
            "code_type",
            "is_primary",
            "is_active",
            "effective_from",
            "effective_to",
            "remark",
            "updated_at",
        } <= set(code.keys()), code
        assert int(code["item_id"]) == int(row["item_id"]), code
        assert isinstance(code["code"], str) and code["code"].strip(), code

    for attr in data["attributes"]:
        assert {
            "attribute_def_id",
            "code",
            "name_cn",
            "value_type",
            "selection_mode",
            "unit",
            "is_item_required",
            "is_sku_required",
            "is_sku_segment",
            "sort_order",
            "value_text",
            "value_number",
            "value_bool",
            "value_option_id",
            "value_option_code_snapshot",
            "value_option_name",
            "value_unit_snapshot",
            "updated_at",
        } <= set(attr.keys()), attr
        assert isinstance(attr["attribute_def_id"], int), attr
        assert isinstance(attr["code"], str) and attr["code"].strip(), attr
        assert isinstance(attr["name_cn"], str) and attr["name_cn"].strip(), attr


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


@pytest.mark.asyncio
async def test_item_list_detail_returns_owner_detail_contract(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/items/list-rows?limit=50", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows, rows

    picked = next((row for row in rows if int(row["uom_count"]) > 0), rows[0])
    item_id = int(picked["item_id"])

    detail_resp = await client.get(f"/items/{item_id}/list-detail", headers=headers)
    assert detail_resp.status_code == 200, detail_resp.text

    detail = detail_resp.json()
    _assert_detail_contract(detail)

    assert int(detail["row"]["item_id"]) == item_id
    assert detail["row"]["sku"] == picked["sku"]


@pytest.mark.asyncio
async def test_item_list_detail_returns_404_for_missing_item(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/items/999999999/list-detail", headers=headers)
    assert r.status_code == 404, r.text
