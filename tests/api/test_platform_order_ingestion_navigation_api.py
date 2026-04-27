from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient


async def _login_admin_headers(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _walk_pages(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def walk(node: dict[str, Any]) -> None:
        out[node["code"]] = node
        for child in node.get("children") or []:
            walk(child)

    for page in pages:
        walk(page)

    return out


def _child_codes(node: dict[str, Any]) -> list[str]:
    return [child["code"] for child in (node.get("children") or [])]


def _index_route_prefixes(route_prefixes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["route_prefix"]: item for item in route_prefixes}


@pytest.mark.asyncio
async def test_platform_order_ingestion_navigation_tree_and_routes(
    client: AsyncClient,
) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    nodes = _walk_pages(data["pages"])
    route_map = _index_route_prefixes(data["route_prefixes"])

    root = nodes.get("platform_order_ingestion")
    assert root is not None
    assert root["name"] == "平台订单采集"
    assert root["parent_code"] is None
    assert root["level"] == 1
    assert root["domain_code"] == "platform_order_ingestion"
    assert root["effective_read_permission"] == "page.platform_order_ingestion.read"
    assert root["effective_write_permission"] == "page.platform_order_ingestion.write"

    assert _child_codes(root) == [
        "platform_order_ingestion.overview",
        "platform_order_ingestion.pdd",
        "platform_order_ingestion.taobao",
        "platform_order_ingestion.jd",
    ]

    assert _child_codes(nodes["platform_order_ingestion.pdd"]) == [
        "platform_order_ingestion.pdd.collect",
        "platform_order_ingestion.pdd.native_orders",
    ]
    assert _child_codes(nodes["platform_order_ingestion.taobao"]) == [
        "platform_order_ingestion.taobao.collect",
        "platform_order_ingestion.taobao.native_orders",
    ]
    assert _child_codes(nodes["platform_order_ingestion.jd"]) == [
        "platform_order_ingestion.jd.collect",
        "platform_order_ingestion.jd.native_orders",
    ]

    expected_route_map = {
        "/platform-order-ingestion": "platform_order_ingestion.overview",
        "/platform-order-ingestion/pdd/collect": "platform_order_ingestion.pdd.collect",
        "/platform-order-ingestion/pdd/native-orders": "platform_order_ingestion.pdd.native_orders",
        "/platform-order-ingestion/taobao/collect": "platform_order_ingestion.taobao.collect",
        "/platform-order-ingestion/taobao/native-orders": "platform_order_ingestion.taobao.native_orders",
        "/platform-order-ingestion/jd/collect": "platform_order_ingestion.jd.collect",
        "/platform-order-ingestion/jd/native-orders": "platform_order_ingestion.jd.native_orders",
    }

    for route_prefix, page_code in expected_route_map.items():
        route = route_map.get(route_prefix)
        assert route is not None, f"{route_prefix} should exist in route_prefixes"
        assert route["page_code"] == page_code
        assert route["effective_read_permission"] == "page.platform_order_ingestion.read"
        assert route["effective_write_permission"] == "page.platform_order_ingestion.write"


@pytest.mark.asyncio
async def test_platform_order_ingestion_navigation_retires_old_oms_platform_pages(
    client: AsyncClient,
) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    nodes = _walk_pages(data["pages"])
    route_map = _index_route_prefixes(data["route_prefixes"])

    assert "oms" not in nodes

    for code in (
        "wms.order_management.pdd_stores",
        "wms.order_management.pdd_orders",
        "wms.order_management.taobao_stores",
        "wms.order_management.taobao_orders",
        "wms.order_management.jd_stores",
        "wms.order_management.jd_orders",
    ):
        assert code not in nodes

    for route_prefix in (
        "/oms/pdd/stores",
        "/oms/pdd/orders",
        "/oms/taobao/stores",
        "/oms/taobao/orders",
        "/oms/jd/stores",
        "/oms/jd/orders",
    ):
        assert route_prefix not in route_map


@pytest.mark.asyncio
async def test_platform_order_ingestion_permission_matrix_uses_independent_root(
    client: AsyncClient,
) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/admin/users/permission-matrix", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    pages = data.get("pages")
    assert isinstance(pages, list)

    page_codes = [item["page_code"] for item in pages]
    assert "platform_order_ingestion" in page_codes
    assert "oms" not in page_codes
