from __future__ import annotations

import httpx
import pytest


def _walk_pages(pages: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}

    def visit(rows: list[dict]) -> None:
        for row in rows:
            out[row["code"]] = row
            visit(row.get("children") or [])

    visit(pages)
    return out


def _route_map(routes: list[dict]) -> dict[str, dict]:
    return {row["route_prefix"]: row for row in routes}


@pytest.mark.asyncio
async def test_pms_sku_coding_page_and_route_exist(client: httpx.AsyncClient) -> None:
    login = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()

    nodes = _walk_pages(data["pages"])
    routes = _route_map(data["route_prefixes"])

    assert nodes["pms.sku_coding"]["name"] == "SKU 编码"
    assert nodes["pms.sku_coding"]["parent_code"] == "pms"
    assert nodes["pms.sku_coding"]["domain_code"] == "pms"
    assert nodes["pms.sku_coding"]["level"] == 2
    assert nodes["pms.sku_coding"]["effective_read_permission"] == "page.pms.read"
    assert nodes["pms.sku_coding"]["effective_write_permission"] == "page.pms.write"
    assert [x["code"] for x in nodes["pms.sku_coding"].get("children", [])] == []

    assert routes["/items/sku-coding"]["page_code"] == "pms.sku_coding"
    assert "/items/sku-coding/generator" not in routes
    assert "/items/sku-coding/dictionaries" not in routes
