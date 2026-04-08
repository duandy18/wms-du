# tests/api/test_admin_user_permission_matrix_save_api.py
#
# 目标：
# - 验证管理员可以保存 /admin/users/{user_id}/permission-matrix
# - 验证 write=true 会自动补 read=true
# - 验证保存时只接管一级页面 page 权限，不破坏矩阵返回结构
#
# 副作用：
# - 会创建一个唯一用户名的测试用户（前缀 zz_admin_matrix_save_）

from __future__ import annotations

import os
from uuid import uuid4

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


def _find_row_by_username(rows: list[dict], username: str) -> dict:
    for row in rows:
        if row.get("username") == username:
            return row
    raise AssertionError(f"未找到用户名={username} 的矩阵行")


def test_admin_can_save_user_permission_matrix(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    username = f"zz_admin_matrix_save_{uuid4().hex[:10]}"

    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": "abc12345",
            "permission_ids": [],
            "full_name": "Matrix Save Test",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    user_id = created["id"]

    save_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "pages": {
                "wms": {"read": False, "write": True},
                "admin": {"read": True, "write": False},
                "oms": {"read": False, "write": False},
                "tms": {"read": False, "write": False},
                "analytics": {"read": False, "write": False},
                "pms": {"read": False, "write": False},
            }
        },
    )
    assert save_resp.status_code == 200, save_resp.text

    saved = save_resp.json()
    assert saved["user_id"] == user_id
    assert saved["username"] == username

    assert saved["pages"]["wms"]["write"] is True
    assert saved["pages"]["wms"]["read"] is True
    assert saved["pages"]["admin"]["read"] is True
    assert saved["pages"]["admin"]["write"] is False
    assert saved["pages"]["oms"]["read"] is False
    assert saved["pages"]["oms"]["write"] is False

    matrix_resp = client.get("/admin/users/permission-matrix", headers=headers)
    assert matrix_resp.status_code == 200, matrix_resp.text

    data = matrix_resp.json()
    rows = data.get("rows")
    assert isinstance(rows, list)

    created_row = _find_row_by_username(rows, username)
    assert created_row["pages"]["wms"]["write"] is True
    assert created_row["pages"]["wms"]["read"] is True
    assert created_row["pages"]["admin"]["read"] is True
    assert created_row["pages"]["admin"]["write"] is False


def test_admin_save_user_permission_matrix_rejects_unknown_page_code(
    client: TestClient,
) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    username = f"zz_admin_matrix_save_{uuid4().hex[:10]}"

    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": "abc12345",
            "permission_ids": [],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    user_id = created["id"]

    save_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "pages": {
                "unknown_domain": {"read": True, "write": False},
            }
        },
    )
    assert save_resp.status_code == 400, save_resp.text
    assert "非法一级页面" in save_resp.text
