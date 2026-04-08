# tests/api/test_admin_navigation_api.py
#
# 目标：
# - 验证 /users/me/navigation 中 admin 根与 admin.users 子页存在
# - 验证 /admin/users 的 route_prefix 映射存在
# - 验证 admin.permissions 与 /admin/permissions 已退役
# - 仅通过 HTTP 调用，不直接写数据库

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


def _ensure_env_dsn() -> None:
    if not os.environ.get("WMS_DATABASE_URL") or not os.environ.get(
        "WMS_TEST_DATABASE_URL"
    ):
        raise RuntimeError(
            "WMS_DATABASE_URL / WMS_TEST_DATABASE_URL 未设置，"
            "请先在终端执行：\n"
            "  export WMS_DATABASE_URL=postgresql+psycopg://wms:wms@127.0.0.1:5433/wms\n"
            "  export WMS_TEST_DATABASE_URL=$WMS_DATABASE_URL\n"
            "再运行 pytest。"
        )


def _login_admin_headers(client: TestClient) -> dict[str, str]:
    login_resp = client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _walk_pages(pages: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}

    def walk(node: dict) -> None:
        out[node["code"]] = node
        for child in node.get("children") or []:
            walk(child)

    for page in pages:
        walk(page)

    return out


def _index_route_prefixes(route_prefixes: list[dict]) -> dict[str, dict]:
    return {item["route_prefix"]: item for item in route_prefixes}


def _child_codes(node: dict) -> list[str]:
    return [child["code"] for child in (node.get("children") or [])]


def test_my_navigation_contains_admin_tree_and_route_prefixes(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    resp = client.get("/users/me/navigation", headers=headers)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert isinstance(data, dict)

    pages = data.get("pages")
    route_prefixes = data.get("route_prefixes")

    assert isinstance(pages, list)
    assert isinstance(route_prefixes, list)

    nodes = _walk_pages(pages)
    route_map = _index_route_prefixes(route_prefixes)

    assert "admin" in nodes
    assert "admin.users" in nodes
    assert "admin.permissions" not in nodes

    admin_root = nodes["admin"]
    assert _child_codes(admin_root) == ["admin.users"]

    users_route = route_map.get("/admin/users")
    permissions_route = route_map.get("/admin/permissions")

    assert users_route is not None
    assert permissions_route is None

    assert users_route["page_code"] == "admin.users"
    assert users_route["effective_read_permission"] == "page.admin.read"
