# tests/api/test_wms_system_iam_snapshot_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _by_code(items: list[dict], key: str) -> dict[str, dict]:
    return {str(item[key]): item for item in items}


def test_wms_system_iam_snapshot_requires_service_client_header() -> None:
    client = TestClient(app)

    response = client.get("/system/read/v1/iam-snapshot")

    assert response.status_code == 401
    assert "wms_service_client_required" in response.text


def test_wms_system_iam_snapshot_rejects_ungranted_service_client() -> None:
    client = TestClient(app)

    response = client.get(
        "/system/read/v1/iam-snapshot",
        headers={"X-Service-Client": "logistics-service"},
    )

    assert response.status_code == 403
    assert "wms_service_permission_denied" in response.text


def test_wms_system_iam_snapshot_returns_safe_projection_for_erp() -> None:
    client = TestClient(app)

    response = client.get(
        "/system/read/v1/iam-snapshot",
        headers={"X-Service-Client": "erp-service"},
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["app_code"] == "wms"
    assert body["app_name"] == "仓储管理"
    assert body["snapshot_at"]

    assert {"users", "permissions", "user_permissions"} <= set(body)
    assert {"page_registry", "page_route_prefixes"} <= set(body)

    users = body["users"]
    permissions = body["permissions"]
    pages = body["page_registry"]
    route_prefixes = body["page_route_prefixes"]

    assert isinstance(users, list)
    assert isinstance(permissions, list)
    assert isinstance(body["user_permissions"], list)
    assert isinstance(pages, list)
    assert isinstance(route_prefixes, list)

    assert users
    assert permissions
    assert pages
    assert route_prefixes

    required_user_keys = {
        "user_id",
        "username",
        "is_active",
        "full_name",
        "phone",
        "email",
    }
    for user in users:
        assert required_user_keys <= set(user)
        assert "password_hash" not in user

    permission_by_code = _by_code(permissions, "permission_code")
    assert "page.wms.read" in permission_by_code
    assert "page.wms.write" in permission_by_code

    page_by_code = _by_code(pages, "page_code")
    root = page_by_code["wms"]
    assert root["page_name"] == "仓储管理"
    assert root["read_permission_code"] == "page.wms.read"
    assert root["write_permission_code"] == "page.wms.write"
    assert root["is_active"] is True

    admin_users = page_by_code["admin.users"]
    assert admin_users["parent_page_code"] == "admin"
    assert admin_users["inherit_permissions"] is True

    route_by_prefix = _by_code(route_prefixes, "route_prefix")
    assert "/admin/users" in route_by_prefix
    assert "/inventory" in route_by_prefix

    body_text = response.text
    assert "password_hash" not in body_text
    assert "token" not in body_text
    assert "secret" not in body_text


def test_wms_system_iam_snapshot_is_registered_in_openapi() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]

    assert "/system/read/v1/iam-snapshot" in paths
    assert "get" in paths["/system/read/v1/iam-snapshot"]
