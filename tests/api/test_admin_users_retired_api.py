from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

LOGIN_BODY = {"username": "admin", "password": "admin123"}


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/users/login", json=LOGIN_BODY)
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _flatten_codes(nodes: list[dict]) -> set[str]:
    out: set[str] = set()

    def walk(items: list[dict]) -> None:
        for item in items:
            code = item.get("code")
            if isinstance(code, str):
                out.add(code)
            children = item.get("children")
            if isinstance(children, list):
                walk(children)

    walk(nodes)
    return out


def test_wms_local_admin_users_routes_are_retired() -> None:
    client = TestClient(app)
    headers = _admin_headers(client)

    for method, path in (
        ("get", "/admin/users"),
        ("get", "/admin/users/permission-matrix"),
        ("post", "/admin/users"),
        ("patch", "/admin/users/1"),
        ("post", "/admin/users/1/delete"),
        ("post", "/admin/users/1/reset-password"),
        ("put", "/admin/users/1/permission-matrix"),
    ):
        if method in {"post", "patch", "put"}:
            response = getattr(client, method)(path, headers=headers, json={})
        else:
            response = getattr(client, method)(path, headers=headers)
        assert response.status_code == 404, (method, path, response.status_code, response.text)


def test_wms_local_admin_users_routes_are_absent_from_openapi() -> None:
    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]

    assert "/admin/users" not in paths
    assert "/admin/users/permission-matrix" not in paths
    assert "/admin/users/{user_id}" not in paths
    assert "/admin/users/{user_id}/delete" not in paths
    assert "/admin/users/{user_id}/reset-password" not in paths
    assert "/admin/users/{user_id}/permission-matrix" not in paths


def test_wms_local_admin_users_navigation_is_retired() -> None:
    client = TestClient(app)
    headers = _admin_headers(client)

    response = client.get("/users/me/navigation", headers=headers)
    assert response.status_code == 200, response.text

    body = response.json()
    codes = _flatten_codes(body["pages"])
    route_prefixes = {item["route_prefix"]: item for item in body["route_prefixes"]}

    assert "admin" not in codes
    assert "admin.users" not in codes
    assert "/admin/users" not in route_prefixes


def test_wms_runtime_user_and_sso_surfaces_remain_registered() -> None:
    client = TestClient(app)
    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]

    assert "/users/login" in paths
    assert "/users/me" in paths
    assert "/users/me/navigation" in paths
    assert "/users/change-password" in paths
    assert "/system/sso/v1/exchange" in paths
    assert "/system/write/v1/iam/apply" in paths
    assert "/system/write/v1/iam/verify" in paths
