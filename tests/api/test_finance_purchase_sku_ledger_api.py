from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _pick_supplier_item(client: httpx.AsyncClient, headers: dict[str, str]) -> int:
    resp = await client.get("/items?supplier_id=1&enabled=true", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert items, items
    return int(items[0]["id"])


async def _pick_purchase_uom(session: AsyncSession, *, item_id: int) -> tuple[int, int]:
    row = (
        await session.execute(
            text(
                """
                SELECT id, ratio_to_base
                  FROM item_uoms
                 WHERE item_id = :item_id
                 ORDER BY is_purchase_default DESC, is_base DESC, id ASC
                 LIMIT 1
                """
            ),
            {"item_id": int(item_id)},
        )
    ).mappings().first()
    assert row is not None
    return int(row["id"]), int(row["ratio_to_base"])


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


@pytest.mark.asyncio
async def test_finance_purchase_sku_ledger_returns_po_line_level_prices_and_accounting_unit_price(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _headers(client)
    item_id = await _pick_supplier_item(client, headers)
    uom_id, ratio_to_base = await _pick_purchase_uom(session, item_id=item_id)

    payload_1 = {
        "warehouse_id": 1,
        "supplier_id": 1,
        "purchaser": "UT",
        "purchase_time": "2036-01-14T10:00:00Z",
        "lines": [
            {
                "line_no": 1,
                "item_id": item_id,
                "uom_id": uom_id,
                "qty_input": 2,
                "supply_price": "2.50",
            }
        ],
    }
    payload_2 = {
        "warehouse_id": 1,
        "supplier_id": 1,
        "purchaser": "UT",
        "purchase_time": "2036-01-14T12:00:00Z",
        "lines": [
            {
                "line_no": 1,
                "item_id": item_id,
                "uom_id": uom_id,
                "qty_input": 1,
                "supply_price": "3.50",
            }
        ],
    }

    created_1 = await client.post("/purchase-orders/", json=payload_1, headers=headers)
    assert created_1.status_code == 200, created_1.text
    po_1 = created_1.json()
    po_line_id_1 = int(po_1["lines"][0]["id"])

    created_2 = await client.post("/purchase-orders/", json=payload_2, headers=headers)
    assert created_2.status_code == 200, created_2.text
    po_2 = created_2.json()
    po_line_id_2 = int(po_2["lines"][0]["id"])

    resp = await client.get(
        "/finance/purchase-costs/sku-purchase-ledger?from_date=2036-01-14&to_date=2036-01-14",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"rows"}
    assert isinstance(body["rows"], list)

    rows_by_id = {int(row["po_line_id"]): row for row in body["rows"]}
    assert po_line_id_1 in rows_by_id, body
    assert po_line_id_2 in rows_by_id, body

    row_1 = rows_by_id[po_line_id_1]
    row_2 = rows_by_id[po_line_id_2]

    expected_fields = {
        "po_line_id",
        "po_id",
        "po_no",
        "line_no",
        "item_id",
        "item_sku",
        "item_name",
        "spec_text",
        "supplier_id",
        "supplier_name",
        "warehouse_id",
        "warehouse_name",
        "purchase_time",
        "purchase_date",
        "qty_ordered_input",
        "purchase_uom_name_snapshot",
        "purchase_ratio_to_base_snapshot",
        "qty_ordered_base",
        "purchase_unit_price",
        "planned_line_amount",
        "accounting_unit_price",
    }
    assert set(row_1) == expected_fields
    assert set(row_2) == expected_fields

    assert row_1["po_no"] == po_1["po_no"]
    assert row_2["po_no"] == po_2["po_no"]
    assert int(row_1["item_id"]) == item_id
    assert int(row_2["item_id"]) == item_id
    assert int(row_1["supplier_id"]) == 1
    assert int(row_2["supplier_id"]) == 1
    assert int(row_1["warehouse_id"]) == 1
    assert int(row_2["warehouse_id"]) == 1
    assert str(row_1["warehouse_name"]).strip()
    assert str(row_2["warehouse_name"]).strip()
    assert row_1["purchase_date"] == "2036-01-14"
    assert row_2["purchase_date"] == "2036-01-14"

    base_qty_1 = 2 * ratio_to_base
    base_qty_2 = 1 * ratio_to_base

    assert int(row_1["qty_ordered_input"]) == 2
    assert int(row_1["purchase_ratio_to_base_snapshot"]) == ratio_to_base
    assert int(row_1["qty_ordered_base"]) == base_qty_1
    assert _decimal(row_1["purchase_unit_price"]) == Decimal("2.50")
    assert _decimal(row_1["planned_line_amount"]) == Decimal("2.50") * Decimal(base_qty_1)

    assert int(row_2["qty_ordered_input"]) == 1
    assert int(row_2["purchase_ratio_to_base_snapshot"]) == ratio_to_base
    assert int(row_2["qty_ordered_base"]) == base_qty_2
    assert _decimal(row_2["purchase_unit_price"]) == Decimal("3.50")
    assert _decimal(row_2["planned_line_amount"]) == Decimal("3.50") * Decimal(base_qty_2)

    expected_accounting_unit_price = (
        (
            Decimal("2.50") * Decimal(base_qty_1)
            + Decimal("3.50") * Decimal(base_qty_2)
        )
        / Decimal(base_qty_1 + base_qty_2)
    ).quantize(Decimal("0.0001"))

    assert _decimal(row_1["accounting_unit_price"]) == expected_accounting_unit_price
    assert _decimal(row_2["accounting_unit_price"]) == expected_accounting_unit_price

    assert "supply_price" not in row_1
    assert "discount_amount" not in row_1
    assert "discount_note" not in row_1
    assert "discount_amount_snapshot" not in row_1


@pytest.mark.asyncio
async def test_finance_purchase_sku_ledger_filters_by_item_keyword_and_supplier(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _headers(client)
    item_id = await _pick_supplier_item(client, headers)
    uom_id, _ratio_to_base = await _pick_purchase_uom(session, item_id=item_id)

    payload = {
        "warehouse_id": 1,
        "supplier_id": 1,
        "purchaser": "UT",
        "purchase_time": "2036-01-15T10:00:00Z",
        "lines": [
            {
                "line_no": 1,
                "item_id": item_id,
                "uom_id": uom_id,
                "qty_input": 1,
                "supply_price": "3.00",
            }
        ],
    }

    created = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert created.status_code == 200, created.text
    po_line_id = int(created.json()["lines"][0]["id"])

    resp = await client.get(
        f"/finance/purchase-costs/sku-purchase-ledger"
        f"?from_date=2036-01-15"
        f"&to_date=2036-01-15"
        f"&supplier_id=1"
        f"&warehouse_id=1"
        f"&item_keyword={item_id}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    rows = resp.json()["rows"]
    assert any(int(row["po_line_id"]) == po_line_id for row in rows), rows


@pytest.mark.asyncio
async def test_finance_purchase_sku_ledger_options_include_items_suppliers_and_warehouses(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _headers(client)
    item_id = await _pick_supplier_item(client, headers)
    uom_id, _ratio_to_base = await _pick_purchase_uom(session, item_id=item_id)

    payload = {
        "warehouse_id": 1,
        "supplier_id": 1,
        "purchaser": "UT",
        "purchase_time": "2036-01-16T10:00:00Z",
        "lines": [
            {
                "line_no": 1,
                "item_id": item_id,
                "uom_id": uom_id,
                "qty_input": 1,
                "supply_price": "4.00",
            }
        ],
    }

    created = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert created.status_code == 200, created.text

    resp = await client.get(
        "/finance/purchase-costs/sku-purchase-ledger/options",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"items", "suppliers", "warehouses"}
    assert any(int(row["item_id"]) == item_id for row in body["items"]), body
    assert any(int(row["supplier_id"]) == 1 for row in body["suppliers"]), body
    assert any(int(row["warehouse_id"]) == 1 for row in body["warehouses"]), body
