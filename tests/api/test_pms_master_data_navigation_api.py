# tests/api/test_pms_master_data_navigation_api.py
from __future__ import annotations

from typing import Any

import httpx
import pytest


async def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _walk_pages(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def walk(node: dict[str, Any]) -> None:
        out[node["code"]] = node
        for child in node.get("children") or []:
            walk(child)

    for page in pages:
        walk(page)

    return out


def _routes(route_prefixes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {x["route_prefix"]: x for x in route_prefixes}


@pytest.mark.asyncio
async def test_pms_master_data_page_tree_and_routes(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    nodes = _walk_pages(data["pages"])
    routes = _routes(data["route_prefixes"])

    assert nodes["pms"]["name"] == "商品主数据"
    assert nodes["pms"]["domain_code"] == "pms"

    expected_children = [
        "pms.items",
        "pms.brands",
        "pms.categories",
        "pms.item_attributes",
        "pms.sku_coding",
        "pms.item_barcodes",
        "pms.item_uoms",
        "pms.suppliers",
    ]
    assert [x["code"] for x in nodes["pms"]["children"]] == expected_children

    assert nodes["pms.items"]["name"] == "商品列表"
    assert nodes["pms.brands"]["name"] == "品牌管理"
    assert nodes["pms.categories"]["name"] == "商品分类编码"
    assert nodes["pms.item_attributes"]["name"] == "属性模板"
    assert nodes["pms.item_uoms"]["name"] == "包装单位"
    assert nodes["pms.suppliers"]["name"] == "供应商管理"

    assert [x["code"] for x in nodes["pms.sku_coding"]["children"]] == [
        "pms.sku_coding.generator",
        "pms.sku_coding.dictionaries",
    ]

    expected_routes = {
        "/items": "pms.items",
        "/pms/brands": "pms.brands",
        "/pms/categories": "pms.categories",
        "/pms/item-attribute-defs": "pms.item_attributes",
        "/items/sku-coding/generator": "pms.sku_coding.generator",
        "/items/sku-coding/dictionaries": "pms.sku_coding.dictionaries",
        "/item-barcodes": "pms.item_barcodes",
        "/item-uoms": "pms.item_uoms",
        "/suppliers": "pms.suppliers",
    }

    for route_prefix, page_code in expected_routes.items():
        route = routes.get(route_prefix)
        assert route is not None, f"{route_prefix} should exist"
        assert route["page_code"] == page_code
        assert route["effective_read_permission"] == "page.pms.read"
        assert route["effective_write_permission"] == "page.pms.write"

    retired_codes = {"wms.masterdata" + ".items", "wms.masterdata" + ".suppliers"}
    assert retired_codes.isdisjoint(nodes.keys())
