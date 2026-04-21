# tests/api/test_user_navigation_api.py
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture(autouse=True)
async def _reset_navigation_registry_state(session: AsyncSession) -> None:
    """
    仅恢复本文件测试会临时修改的导航状态，不破坏静态 seed 真相。

    当前主线要求：
    - tms 下子页在相关测试前恢复为可见
    - wms.inventory_adjustment 下子页保持可见
    - wms.inbound 只保留 atomic / purchase / manual 可见
    - wms.inbound.operations / wms.inbound.returns 保持隐藏
    - inbound 只保留 summary / purchase / manual 可见
    """
    await session.execute(
        text(
            """
            UPDATE page_registry
               SET is_active = TRUE
             WHERE parent_code = 'tms'
            """
        )
    )

    await session.execute(
        text(
            """
            UPDATE page_registry
               SET is_active = TRUE
             WHERE parent_code = 'wms.inventory_adjustment'
            """
        )
    )

    await session.execute(
        text(
            """
            UPDATE page_registry
               SET is_active = TRUE
             WHERE code IN (
               'wms.inbound.atomic',
               'wms.inbound.purchase',
               'wms.inbound.manual',
               'inbound.summary',
               'inbound.purchase',
               'inbound.manual'
             )
            """
        )
    )

    await session.execute(
        text(
            """
            UPDATE page_registry
               SET is_active = FALSE
             WHERE code IN (
               'wms.inbound.operations',
               'wms.inbound.returns',
               'inbound.returns'
             )
            """
        )
    )

    await session.execute(
        text(
            """
            UPDATE page_route_prefixes
               SET is_active = TRUE
             WHERE route_prefix LIKE '/tms/%'
                OR route_prefix LIKE '/inventory-adjustment%'
            """
        )
    )

    await session.commit()


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


def _index_route_prefixes(route_prefixes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["route_prefix"]: item for item in route_prefixes}


def _child_codes(node: dict[str, Any]) -> list[str]:
    return [child["code"] for child in (node.get("children") or [])]


async def _set_user_permissions_by_names(
    session: AsyncSession,
    *,
    username: str,
    permission_names: list[str],
) -> None:
    await session.execute(
        text(
            """
            DELETE FROM user_permissions
             WHERE user_id = (
                SELECT id
                  FROM users
                 WHERE username = :username
                 LIMIT 1
             )
            """
        ),
        {"username": username},
    )

    if permission_names:
        await session.execute(
            text(
                """
                INSERT INTO user_permissions (user_id, permission_id)
                SELECT u.id, p.id
                  FROM users u
                  JOIN permissions p
                    ON p.name = ANY(CAST(:permission_names AS text[]))
                 WHERE u.username = :username
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "username": username,
                "permission_names": permission_names,
            },
        )

    await session.commit()


@pytest.mark.asyncio
async def test_my_me_shape_unchanged(client: AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    assert isinstance(data, dict)

    assert {"id", "username", "permissions"} <= set(data.keys())
    assert isinstance(data["id"], int)
    assert isinstance(data["username"], str)
    assert isinstance(data["permissions"], list)
    assert "page.admin.read" in data["permissions"]
    assert "page.admin.write" in data["permissions"]


@pytest.mark.asyncio
async def test_my_navigation_returns_pages_and_route_prefixes(client: AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    assert isinstance(data, dict)

    pages = data.get("pages")
    route_prefixes = data.get("route_prefixes")

    assert isinstance(pages, list)
    assert isinstance(route_prefixes, list)
    assert pages, "pages should not be empty for admin"
    assert route_prefixes, "route_prefixes should not be empty for admin"


@pytest.mark.asyncio
async def test_my_navigation_admin_contains_new_wms_tree_and_filters_legacy_shells(
    client: AsyncClient,
) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    pages = data["pages"]
    nodes = _walk_pages(pages)

    root_codes = [page["code"] for page in pages]
    assert "wms" in root_codes
    assert "inbound" in root_codes

    wms = nodes["wms"]
    assert _child_codes(wms) == [
        "wms.inventory",
        "wms.inbound",
        "wms.outbound",
        "wms.inventory_adjustment",
        "wms.warehouses",
    ]

    assert _child_codes(nodes["wms.inventory"]) == [
        "wms.inventory.main",
        "wms.inventory.ledger",
    ]
    assert _child_codes(nodes["wms.inbound"]) == [
        "wms.inbound.atomic",
        "wms.inbound.purchase",
        "wms.inbound.manual",
    ]
    assert _child_codes(nodes["wms.outbound"]) == [
        "wms.outbound.summary",
        "wms.outbound.order",
        "wms.outbound.manual_docs",
        "wms.outbound.manual",
    ]
    assert _child_codes(nodes["wms.inventory_adjustment"]) == [
        "wms.inventory_adjustment.summary",
        "wms.inventory_adjustment.count",
        "wms.inventory_adjustment.inbound_reversal",
        "wms.inventory_adjustment.outbound_reversal",
        "wms.inventory_adjustment.return_inbound",
    ]
    assert _child_codes(nodes["wms.warehouses"]) == []

    assert _child_codes(nodes["inbound"]) == [
        "inbound.summary",
        "inbound.purchase",
        "inbound.manual",
    ]

    assert "wms.count" not in nodes
    assert "wms.count.tasks" not in nodes
    assert "wms.count.adjustments" not in nodes
    assert "wms.inbound.returns" not in nodes
    assert "inbound.returns" not in nodes

    assert "wms.order_outbound" not in nodes
    assert "wms.order_management" not in nodes
    assert "wms.logistics" not in nodes
    assert "wms.analytics" not in nodes
    assert "wms.masterdata" not in nodes
    assert "wms.internal_ops" not in nodes
    assert "wms.inbound.receiving" not in nodes
    assert "wms.internal_ops.count" not in nodes
    assert "wms.internal_ops.internal_outbound" not in nodes
    assert "wms.order_outbound.pick_tasks" not in nodes
    assert "wms.order_outbound.dashboard" not in nodes
    assert "wms.masterdata.warehouses" not in nodes


@pytest.mark.asyncio
async def test_my_navigation_masterdata_and_wms_warehouses_domain_codes_are_correct(
    client: AsyncClient,
) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    nodes = _walk_pages(data["pages"])

    pms_root = nodes.get("pms")
    assert pms_root is not None, "pms parent should exist"

    items = nodes.get("wms.masterdata.items")
    suppliers = nodes.get("wms.masterdata.suppliers")
    warehouses = nodes.get("wms.warehouses")

    assert items is not None, "wms.masterdata.items should exist"
    assert suppliers is not None, "wms.masterdata.suppliers should exist"
    assert warehouses is not None, "wms.warehouses should exist"

    assert items["parent_code"] == "pms"
    assert suppliers["parent_code"] == "pms"
    assert warehouses["parent_code"] == "wms"

    assert items["domain_code"] == "pms"
    assert suppliers["domain_code"] == "pms"
    assert warehouses["domain_code"] == "wms"

    assert "wms.masterdata" not in nodes
    assert "wms.masterdata.warehouses" not in nodes


@pytest.mark.asyncio
async def test_my_navigation_item_barcodes_page_is_under_pms(client: AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    nodes = _walk_pages(data["pages"])

    item_barcodes = nodes.get("pms.item_barcodes")
    assert item_barcodes is not None, "pms.item_barcodes should exist"

    assert item_barcodes["parent_code"] == "pms"
    assert item_barcodes["domain_code"] == "pms"
    assert item_barcodes["effective_read_permission"] == "page.pms.read"
    assert item_barcodes["effective_write_permission"] == "page.pms.write"


@pytest.mark.asyncio
async def test_my_navigation_route_prefix_mapping_and_effective_permissions(client: AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    nodes = _walk_pages(data["pages"])
    route_map = _index_route_prefixes(data["route_prefixes"])

    pricing_page = nodes["wms.logistics.pricing"]
    items_page = nodes["wms.masterdata.items"]
    suppliers_page = nodes["wms.masterdata.suppliers"]
    inventory_page = nodes["wms.inventory.main"]
    warehouses_page = nodes["wms.warehouses"]
    inventory_adjustment_page = nodes["wms.inventory_adjustment.summary"]
    inventory_return_inbound_page = nodes["wms.inventory_adjustment.return_inbound"]

    assert pricing_page["effective_read_permission"] == "page.tms.read"
    assert pricing_page["effective_write_permission"] == "page.tms.write"

    assert items_page["effective_read_permission"] == "page.pms.read"
    assert items_page["effective_write_permission"] == "page.pms.write"

    assert suppliers_page["effective_read_permission"] == "page.pms.read"
    assert suppliers_page["effective_write_permission"] == "page.pms.write"

    assert inventory_page["effective_read_permission"] == "page.wms.read"
    assert inventory_page["effective_write_permission"] == "page.wms.write"

    assert warehouses_page["effective_read_permission"] == "page.wms.read"
    assert warehouses_page["effective_write_permission"] == "page.wms.write"

    assert inventory_adjustment_page["effective_read_permission"] == "page.wms.read"
    assert inventory_adjustment_page["effective_write_permission"] == "page.wms.write"

    assert inventory_return_inbound_page["effective_read_permission"] == "page.wms.read"
    assert inventory_return_inbound_page["effective_write_permission"] == "page.wms.write"

    pricing_route = route_map.get("/tms/pricing")
    items_route = route_map.get("/items")
    suppliers_route = route_map.get("/suppliers")
    inventory_route = route_map.get("/inventory")
    warehouses_route = route_map.get("/warehouses")
    inventory_adjustment_route = route_map.get("/inventory-adjustment")
    inventory_return_inbound_route = route_map.get("/inventory-adjustment/return-inbound")

    assert pricing_route is not None, "/tms/pricing should exist in route_prefixes"
    assert items_route is not None, "/items should exist in route_prefixes"
    assert suppliers_route is not None, "/suppliers should exist in route_prefixes"
    assert inventory_route is not None, "/inventory should exist in route_prefixes"
    assert warehouses_route is not None, "/warehouses should exist in route_prefixes"
    assert inventory_adjustment_route is not None, "/inventory-adjustment should exist in route_prefixes"
    assert inventory_return_inbound_route is not None, "/inventory-adjustment/return-inbound should exist in route_prefixes"

    assert pricing_route["page_code"] == "wms.logistics.pricing"
    assert items_route["page_code"] == "wms.masterdata.items"
    assert suppliers_route["page_code"] == "wms.masterdata.suppliers"
    assert inventory_route["page_code"] == "wms.inventory.main"
    assert warehouses_route["page_code"] == "wms.warehouses"
    assert inventory_adjustment_route["page_code"] == "wms.inventory_adjustment.summary"
    assert inventory_return_inbound_route["page_code"] == "wms.inventory_adjustment.return_inbound"

    assert pricing_route["effective_read_permission"] == "page.tms.read"
    assert pricing_route["effective_write_permission"] == "page.tms.write"

    assert items_route["effective_read_permission"] == "page.pms.read"
    assert items_route["effective_write_permission"] == "page.pms.write"

    assert suppliers_route["effective_read_permission"] == "page.pms.read"
    assert suppliers_route["effective_write_permission"] == "page.pms.write"

    assert inventory_route["effective_read_permission"] == "page.wms.read"
    assert inventory_route["effective_write_permission"] == "page.wms.write"

    assert warehouses_route["effective_read_permission"] == "page.wms.read"
    assert warehouses_route["effective_write_permission"] == "page.wms.write"

    assert inventory_adjustment_route["effective_read_permission"] == "page.wms.read"
    assert inventory_adjustment_route["effective_write_permission"] == "page.wms.write"

    assert inventory_return_inbound_route["effective_read_permission"] == "page.wms.read"
    assert inventory_return_inbound_route["effective_write_permission"] == "page.wms.write"


@pytest.mark.asyncio
async def test_my_navigation_item_barcodes_route_prefix_mapping_and_permissions(
    client: AsyncClient,
) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    route_map = _index_route_prefixes(data["route_prefixes"])

    item_barcodes_route = route_map.get("/item-barcodes")
    assert item_barcodes_route is not None, "/item-barcodes should exist in route_prefixes"

    assert item_barcodes_route["page_code"] == "pms.item_barcodes"
    assert item_barcodes_route["effective_read_permission"] == "page.pms.read"
    assert item_barcodes_route["effective_write_permission"] == "page.pms.write"


@pytest.mark.asyncio
async def test_my_navigation_filters_to_only_directly_visible_parent_tree(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await _set_user_permissions_by_names(
        session,
        username="admin",
        permission_names=["page.tms.read"],
    )

    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    pages = data["pages"]
    route_prefixes = data["route_prefixes"]

    assert [page["code"] for page in pages] == ["tms"]

    parent = pages[0]
    child_codes = [child["code"] for child in parent["children"]]
    assert child_codes == [
        "wms.logistics.shipment_prepare",
        "wms.logistics.dispatch",
        "wms.logistics.providers",
        "wms.logistics.waybill_configs",
        "wms.logistics.pricing",
        "wms.logistics.templates",
        "wms.logistics.records",
        "wms.logistics.billing_items",
        "wms.logistics.reconciliation",
        "wms.logistics.reports",
    ]

    assert all(item["page_code"].startswith("wms.logistics.") for item in route_prefixes)
    assert [item["route_prefix"] for item in route_prefixes] == [
        "/tms/shipment-prepare",
        "/tms/dispatch",
        "/tms/providers",
        "/tms/waybill-configs",
        "/tms/pricing",
        "/tms/templates",
        "/tms/records",
        "/tms/billing/items",
        "/tms/reconciliation",
        "/tms/reports",
    ]


@pytest.mark.asyncio
async def test_my_navigation_keeps_parent_visible_when_no_visible_children(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    await _set_user_permissions_by_names(
        session,
        username="admin",
        permission_names=["page.tms.read"],
    )

    await session.execute(
        text(
            """
            UPDATE page_registry
               SET is_active = FALSE
             WHERE parent_code = 'tms'
            """
        )
    )
    await session.commit()

    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    assert [page["code"] for page in data["pages"]] == ["tms"]
    assert data["pages"][0]["children"] == []
    assert data["route_prefixes"] == []
