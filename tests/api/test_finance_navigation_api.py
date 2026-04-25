from __future__ import annotations

from typing import Any


async def _headers(client) -> dict[str, str]:
    login = await client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _flatten_pages(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def walk(node: dict[str, Any]) -> None:
        code = str(node.get("code") or "")
        if code:
            out[code] = node
        children = node.get("children") or []
        assert isinstance(children, list), node
        for child in children:
            assert isinstance(child, dict), child
            walk(child)

    for page in pages:
        walk(page)

    return out


async def test_finance_navigation_contract_is_terminal(client):
    headers = await _headers(client)

    resp = await client.get("/users/me/navigation", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    pages = body.get("pages") or []
    routes = body.get("route_prefixes") or []

    page_by_code = _flatten_pages(pages)
    route_by_prefix = {r["route_prefix"]: r for r in routes}

    assert "finance" in page_by_code
    assert "finance.overview" in page_by_code
    assert "finance.order_sales" in page_by_code
    assert "finance.purchase_cost" in page_by_code
    assert "finance.shipping_cost" in page_by_code

    assert "analytics" not in page_by_code
    assert "analytics.finance" not in page_by_code
    assert "wms.analytics.finance" not in page_by_code

    root = page_by_code["finance"]
    assert root["name"] == "财务分析"
    assert root["parent_code"] is None
    assert root["domain_code"] == "finance"
    assert root["effective_read_permission"] == "page.finance.read"
    assert root["effective_write_permission"] == "page.finance.write"

    overview = page_by_code["finance.overview"]
    assert overview["name"] == "综合分析"
    assert overview["parent_code"] == "finance"
    assert overview["domain_code"] == "finance"
    assert overview["effective_read_permission"] == "page.finance.read"
    assert overview["effective_write_permission"] == "page.finance.write"

    order_sales = page_by_code["finance.order_sales"]
    assert order_sales["name"] == "订单销售"
    assert order_sales["parent_code"] == "finance"
    assert order_sales["domain_code"] == "finance"
    assert order_sales["effective_read_permission"] == "page.finance.read"
    assert order_sales["effective_write_permission"] == "page.finance.write"

    purchase_cost = page_by_code["finance.purchase_cost"]
    assert purchase_cost["name"] == "采购成本"
    assert purchase_cost["parent_code"] == "finance"
    assert purchase_cost["domain_code"] == "finance"
    assert purchase_cost["effective_read_permission"] == "page.finance.read"
    assert purchase_cost["effective_write_permission"] == "page.finance.write"

    shipping_cost = page_by_code["finance.shipping_cost"]
    assert shipping_cost["name"] == "物流成本"
    assert shipping_cost["parent_code"] == "finance"
    assert shipping_cost["domain_code"] == "finance"
    assert shipping_cost["effective_read_permission"] == "page.finance.read"
    assert shipping_cost["effective_write_permission"] == "page.finance.write"

    assert route_by_prefix["/finance"]["page_code"] == "finance.overview"
    assert route_by_prefix["/finance"]["effective_read_permission"] == "page.finance.read"
    assert route_by_prefix["/finance"]["effective_write_permission"] == "page.finance.write"

    assert route_by_prefix["/finance/order-sales"]["page_code"] == "finance.order_sales"
    assert route_by_prefix["/finance/order-sales"]["effective_read_permission"] == "page.finance.read"
    assert route_by_prefix["/finance/order-sales"]["effective_write_permission"] == "page.finance.write"

    assert route_by_prefix["/finance/purchase-costs"]["page_code"] == "finance.purchase_cost"
    assert route_by_prefix["/finance/purchase-costs"]["effective_read_permission"] == "page.finance.read"
    assert route_by_prefix["/finance/purchase-costs"]["effective_write_permission"] == "page.finance.write"

    assert route_by_prefix["/finance/shipping-costs"]["page_code"] == "finance.shipping_cost"
    assert route_by_prefix["/finance/shipping-costs"]["effective_read_permission"] == "page.finance.read"
    assert route_by_prefix["/finance/shipping-costs"]["effective_write_permission"] == "page.finance.write"

    assert "/finance/overview" not in route_by_prefix
    assert "/finance/shop" not in route_by_prefix
    assert "/finance/sku" not in route_by_prefix
    assert "/finance/order-unit" not in route_by_prefix
