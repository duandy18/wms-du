# tests/api/test_admin_users_read_only_api.py
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


def _ensure_env_dsn() -> None:
    if not os.environ.get("WMS_DATABASE_URL") or not os.environ.get("WMS_TEST_DATABASE_URL"):
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


def test_admin_users_read_routes_still_work(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    users_resp = client.get("/admin/users", headers=headers)
    assert users_resp.status_code == 200, users_resp.text
    users = users_resp.json()
    assert isinstance(users, list)
    assert users

    first = users[0]
    assert {"id", "username", "is_active", "permissions"} <= set(first)

    matrix_resp = client.get("/admin/users/permission-matrix", headers=headers)
    assert matrix_resp.status_code == 200, matrix_resp.text
    matrix = matrix_resp.json()
    assert isinstance(matrix.get("pages"), list)
    assert isinstance(matrix.get("rows"), list)


def test_admin_user_write_routes_are_removed_from_openapi(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text

    paths = response.json()["paths"]

    assert "get" in paths["/admin/users"]
    assert "post" not in paths["/admin/users"]

    assert "/admin/users/{user_id}" not in paths
    assert "/admin/users/{user_id}/delete" not in paths
    assert "/admin/users/{user_id}/reset-password" not in paths
    assert "/admin/users/{user_id}/permission-matrix" not in paths


def test_admin_user_write_routes_return_not_available(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    post_resp = client.post(
        "/admin/users",
        headers=headers,
        json={"username": "zz_should_not_create", "password": "abc12345"},
    )
    assert post_resp.status_code == 405

    patch_resp = client.patch(
        "/admin/users/1",
        headers=headers,
        json={"full_name": "should not update"},
    )
    assert patch_resp.status_code == 404

    delete_resp = client.post("/admin/users/1/delete", headers=headers)
    assert delete_resp.status_code == 404

    reset_resp = client.post("/admin/users/1/reset-password", headers=headers, json={})
    assert reset_resp.status_code == 404

    matrix_write_resp = client.put(
        "/admin/users/1/permission-matrix",
        headers=headers,
        json={"page_codes": [], "pages": {}},
    )
    assert matrix_write_resp.status_code == 404
