# tests/api/test_pms_sku_coding_navigation_api.py
from __future__ import annotations

import httpx
import pytest


def _walk_pages(pages: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}

    def walk(node: dict) -> None:
        out[str(node["code"])] = node
        for child in node.get("children") or []:
            walk(child)

    for page in pages:
        walk(page)
    return out


def _route_map(route_prefixes: list[dict]) -> dict[str, dict]:
    return {str(row["route_prefix"]): row for row in route_prefixes}


@pytest.mark.asyncio
async def test_pms_sku_coding_pages_and_routes_exist(client: httpx.AsyncClient) -> None:
    login = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    nodes = _walk_pages(data["pages"])
    routes = _route_map(data["route_prefixes"])

    assert nodes["pms.sku_coding"]["parent_code"] == "pms"
    assert nodes["pms.sku_coding"]["domain_code"] == "pms"

    assert nodes["pms.sku_coding.generator"]["parent_code"] == "pms.sku_coding"
    assert nodes["pms.sku_coding.generator"]["effective_read_permission"] == "page.pms.read"
    assert nodes["pms.sku_coding.generator"]["effective_write_permission"] == "page.pms.write"

    assert nodes["pms.sku_coding.dictionaries"]["parent_code"] == "pms.sku_coding"
    assert nodes["pms.sku_coding.dictionaries"]["effective_read_permission"] == "page.pms.read"
    assert nodes["pms.sku_coding.dictionaries"]["effective_write_permission"] == "page.pms.write"

    assert routes["/items/sku-coding/generator"]["page_code"] == "pms.sku_coding.generator"
    assert routes["/items/sku-coding/dictionaries"]["page_code"] == "pms.sku_coding.dictionaries"
