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
    导航测试会临时改 page_registry.is_active。
    但 tests baseline 不会 TRUNCATE page_registry / page_route_prefixes，
    所以这里在每个用例开始前显式恢复静态导航表状态，避免状态串到后续用例。
    """
    await session.execute(
        text(
            "UPDATE page_registry SET is_active = TRUE WHERE is_active IS DISTINCT FROM TRUE"
        )
    )
    await session.execute(
        text(
            "UPDATE page_route_prefixes SET is_active = TRUE WHERE is_active IS DISTINCT FROM TRUE"
        )
    )
    await session.commit()


async def _login_admin_headers(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _index_pages(
    pages: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    parents: dict[str, dict[str, Any]] = {}
    children: dict[str, dict[str, Any]] = {}

    for parent in pages:
        parents[parent["code"]] = parent
        for child in parent.get("children") or []:
            children[child["code"]] = child

    return parents, children


def _index_route_prefixes(
    route_prefixes: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {item["route_prefix"]: item for item in route_prefixes}


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

    assert set(data.keys()) == {"id", "username", "permissions"}
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
async def test_my_navigation_admin_baseline_counts(client: AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    pages = data["pages"]
    route_prefixes = data["route_prefixes"]

    assert len(pages) == 10

    child_count = sum(len(page.get("children") or []) for page in pages)
    assert child_count == 29

    assert len(route_prefixes) == 30


@pytest.mark.asyncio
async def test_my_navigation_masterdata_domain_codes_are_correct(client: AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    parents, children = _index_pages(data["pages"])

    pms = parents.get("pms")
    masterdata = parents.get("wms.masterdata")

    assert pms is not None, "pms parent should exist"
    assert masterdata is not None, "wms.masterdata parent should exist"

    items = children.get("wms.masterdata.items")
    suppliers = children.get("wms.masterdata.suppliers")
    warehouses = children.get("wms.masterdata.warehouses")

    assert items is not None, "wms.masterdata.items should exist"
    assert suppliers is not None, "wms.masterdata.suppliers should exist"
    assert warehouses is not None, "wms.masterdata.warehouses should exist"

    assert items["parent_code"] == "pms"
    assert suppliers["parent_code"] == "pms"
    assert warehouses["parent_code"] == "wms.masterdata"

    assert items["domain_code"] == "pms"
    assert suppliers["domain_code"] == "pms"
    assert warehouses["domain_code"] == "wms"


@pytest.mark.asyncio
async def test_my_navigation_route_prefix_mapping_and_effective_permissions(
    client: AsyncClient,
) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/users/me/navigation", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    _, children = _index_pages(data["pages"])
    route_map = _index_route_prefixes(data["route_prefixes"])

    finance_page = children["wms.analytics.finance"]
    pricing_page = children["wms.logistics.pricing"]
    items_page = children["wms.masterdata.items"]
    suppliers_page = children["wms.masterdata.suppliers"]
    admin_users_page = children["admin.users"]
    admin_permissions_page = children["admin.permissions"]

    assert finance_page["effective_read_permission"] == "page.analytics.read"
    assert finance_page["effective_write_permission"] == "page.analytics.write"

    assert pricing_page["effective_read_permission"] == "page.tms.read"
    assert pricing_page["effective_write_permission"] == "page.tms.write"

    assert items_page["effective_read_permission"] == "page.pms.read"
    assert items_page["effective_write_permission"] == "page.pms.write"

    assert suppliers_page["effective_read_permission"] == "page.pms.read"
    assert suppliers_page["effective_write_permission"] == "page.pms.write"

    assert admin_users_page["effective_read_permission"] == "page.admin.read"
    assert admin_users_page["effective_write_permission"] == "page.admin.write"

    assert admin_permissions_page["effective_read_permission"] == "page.admin.read"
    assert admin_permissions_page["effective_write_permission"] == "page.admin.write"

    finance_route = route_map.get("/finance")
    pricing_route = route_map.get("/tms/pricing")
    items_route = route_map.get("/items")
    suppliers_route = route_map.get("/suppliers")
    admin_users_route = route_map.get("/admin/users")
    admin_permissions_route = route_map.get("/admin/permissions")

    assert finance_route is not None, "/finance should exist in route_prefixes"
    assert pricing_route is not None, "/tms/pricing should exist in route_prefixes"
    assert items_route is not None, "/items should exist in route_prefixes"
    assert suppliers_route is not None, "/suppliers should exist in route_prefixes"
    assert admin_users_route is not None, "/admin/users should exist in route_prefixes"
    assert (
        admin_permissions_route is not None
    ), "/admin/permissions should exist in route_prefixes"

    assert finance_route["page_code"] == "wms.analytics.finance"
    assert pricing_route["page_code"] == "wms.logistics.pricing"
    assert items_route["page_code"] == "wms.masterdata.items"
    assert suppliers_route["page_code"] == "wms.masterdata.suppliers"
    assert admin_users_route["page_code"] == "admin.users"
    assert admin_permissions_route["page_code"] == "admin.permissions"

    assert finance_route["effective_read_permission"] == "page.analytics.read"
    assert finance_route["effective_write_permission"] == "page.analytics.write"

    assert pricing_route["effective_read_permission"] == "page.tms.read"
    assert pricing_route["effective_write_permission"] == "page.tms.write"

    assert items_route["effective_read_permission"] == "page.pms.read"
    assert items_route["effective_write_permission"] == "page.pms.write"

    assert suppliers_route["effective_read_permission"] == "page.pms.read"
    assert suppliers_route["effective_write_permission"] == "page.pms.write"

    assert admin_users_route["effective_read_permission"] == "page.admin.read"
    assert admin_users_route["effective_write_permission"] == "page.admin.write"

    assert admin_permissions_route["effective_read_permission"] == "page.admin.read"
    assert admin_permissions_route["effective_write_permission"] == "page.admin.write"


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
async def test_my_navigation_hides_parent_when_no_visible_children(
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
    assert data["pages"] == []
    assert data["route_prefixes"] == []
