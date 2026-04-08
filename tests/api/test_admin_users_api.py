# tests/api/test_admin_users_api.py
#
# 目标：
# - 验证管理员用户管理接口已经收口到 /admin/users
# - 验证授权调整通过 /admin/users/{user_id}/permission-matrix 完成
# - 仅通过 HTTP 调用，不直接写数据库
#
# 副作用：
# - 会创建一个唯一用户名的测试用户（前缀 zz_admin_api_）

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


def _find_user_by_username(rows: list[dict], username: str) -> dict:
    for row in rows:
        if row.get("username") == username:
            return row
    raise AssertionError(f"未找到用户名={username} 的用户行")


def test_admin_can_list_users_via_admin_users(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    resp = client.get("/admin/users", headers=headers)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert isinstance(data, list)
    assert data, "admin/users should not be empty"

    first = data[0]
    assert isinstance(first, dict)
    assert {"id", "username", "permissions"} <= set(first.keys())


def test_admin_can_create_update_save_matrix_and_reset_password(
    client: TestClient,
) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    username = f"zz_admin_api_{uuid4().hex[:10]}"
    initial_password = "abc12345"

    # 1) 创建用户（初始不给页面权限）
    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": initial_password,
            "permission_ids": [],
            "full_name": "Admin API Test",
            "phone": "13800000000",
            "email": f"{username}@example.com",
        },
    )
    assert create_resp.status_code == 201, create_resp.text

    created = create_resp.json()
    assert created["username"] == username
    assert created["full_name"] == "Admin API Test"
    assert created["email"] == f"{username}@example.com"
    assert isinstance(created.get("permissions"), list)
    assert "page.admin.read" not in created["permissions"]
    assert "page.admin.write" not in created["permissions"]

    user_id = created["id"]
    assert isinstance(user_id, int)

    # 2) 更新基础信息
    update_resp = client.patch(
        f"/admin/users/{user_id}",
        headers=headers,
        json={
            "full_name": "Admin API Test Updated",
            "phone": "13900000000",
            "email": f"{username}.updated@example.com",
        },
    )
    assert update_resp.status_code == 200, update_resp.text

    updated = update_resp.json()
    assert updated["id"] == user_id
    assert updated["full_name"] == "Admin API Test Updated"
    assert updated["phone"] == "13900000000"
    assert updated["email"] == f"{username}.updated@example.com"

    # 3) 通过矩阵授予 admin 写权限；write=true 应自动补 read=true
    matrix_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "pages": {
                "admin": {"read": False, "write": True},
                "wms": {"read": False, "write": False},
                "oms": {"read": False, "write": False},
                "tms": {"read": False, "write": False},
                "analytics": {"read": False, "write": False},
                "pms": {"read": False, "write": False},
            }
        },
    )
    assert matrix_resp.status_code == 200, matrix_resp.text

    saved = matrix_resp.json()
    assert saved["user_id"] == user_id
    assert saved["username"] == username
    assert saved["pages"]["admin"]["write"] is True
    assert saved["pages"]["admin"]["read"] is True

    # 4) 用户列表里应能看到已经落到真实 permissions
    users_resp = client.get("/admin/users", headers=headers)
    assert users_resp.status_code == 200, users_resp.text

    users = users_resp.json()
    assert isinstance(users, list)

    saved_user = _find_user_by_username(users, username)
    assert saved_user["id"] == user_id
    assert saved_user["full_name"] == "Admin API Test Updated"
    assert saved_user["phone"] == "13900000000"
    assert saved_user["email"] == f"{username}.updated@example.com"
    assert "page.admin.read" in saved_user["permissions"]
    assert "page.admin.write" in saved_user["permissions"]

    # 5) 重置密码
    reset_resp = client.post(
        f"/admin/users/{user_id}/reset-password",
        headers=headers,
        json={},
    )
    assert reset_resp.status_code == 200, reset_resp.text

    reset_data = reset_resp.json()
    assert reset_data["ok"] is True

    # 6) 使用重置后的密码登录
    login_resp = client.post(
        "/users/login",
        json={"username": username, "password": "000000"},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert "access_token" in login_resp.json()
