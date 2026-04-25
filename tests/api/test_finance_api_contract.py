from __future__ import annotations


async def _headers(client) -> dict[str, str]:
    login = await client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_finance_overview_page_contract(client):
    headers = await _headers(client)

    resp = await client.get(
        "/finance/overview?from_date=2026-01-01&to_date=2026-01-07",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"summary", "daily"}

    assert set(body["summary"]) == {
        "revenue",
        "purchase_cost",
        "shipping_cost",
        "gross_profit",
        "gross_margin",
        "fulfillment_ratio",
    }

    assert isinstance(body["daily"], list)
    assert body["daily"], body
    assert set(body["daily"][0]) == {
        "day",
        "revenue",
        "purchase_cost",
        "shipping_cost",
        "gross_profit",
        "gross_margin",
        "fulfillment_ratio",
    }


async def test_finance_order_sales_contract(client):
    headers = await _headers(client)

    resp = await client.get(
        "/finance/order-sales?from_date=2026-01-01&to_date=2026-01-07",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"summary", "daily", "by_shop", "by_item", "top_orders"}
    assert set(body["summary"]) == {
        "order_count",
        "revenue",
        "avg_order_value",
        "median_order_value",
    }
    assert isinstance(body["daily"], list)
    assert isinstance(body["by_shop"], list)
    assert isinstance(body["by_item"], list)
    assert isinstance(body["top_orders"], list)


async def test_finance_purchase_costs_contract(client):
    headers = await _headers(client)

    resp = await client.get(
        "/finance/purchase-costs?from_date=2026-01-01&to_date=2026-01-07",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"summary", "daily", "by_supplier", "by_item"}
    assert set(body["summary"]) == {
        "purchase_order_count",
        "supplier_count",
        "item_count",
        "purchase_amount",
        "avg_unit_cost",
    }
    assert isinstance(body["daily"], list)
    assert isinstance(body["by_supplier"], list)
    assert isinstance(body["by_item"], list)


async def test_finance_shipping_costs_contract(client):
    headers = await _headers(client)

    resp = await client.get(
        "/finance/shipping-costs?from_date=2026-01-01&to_date=2026-01-07",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body) == {"summary", "daily", "by_carrier", "by_shop"}
    assert set(body["summary"]) == {
        "shipment_count",
        "estimated_shipping_cost",
        "billed_shipping_cost",
        "cost_diff",
        "adjusted_cost",
    }
    assert isinstance(body["daily"], list)
    assert isinstance(body["by_carrier"], list)
    assert isinstance(body["by_shop"], list)


async def test_legacy_finance_routes_are_not_kept(client):
    headers = await _headers(client)

    legacy_paths = [
        "/finance/overview/daily",
        "/finance/shop",
        "/finance/sku",
        "/finance/order-unit",
    ]

    for path in legacy_paths:
        resp = await client.get(path, headers=headers)
        assert resp.status_code == 404, f"{path} should be retired: {resp.text}"
