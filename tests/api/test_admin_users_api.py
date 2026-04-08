# tests/api/test_admin_users_api.py
#
# 目标：
# - 验证管理员用户管理接口已经收口到 /admin/users
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


def _get_permission_ids_by_name(
    client: TestClient,
    headers: dict[str, str],
) -> dict[str, int]:
    r = client.get("/admin/permissions", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    assert isinstance(data, list)

    out: dict[str, int] = {}
    for item in data:
        name = item.get("name")
        pid = item.get("id")
        if isinstance(name, str) and isinstance(pid, int):
            out[name] = pid
    return out


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


def test_admin_can_create_update_set_permissions_and_reset_password(
    client: TestClient,
) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    permission_ids = _get_permission_ids_by_name(client, headers)
    assert "page.admin.read" in permission_ids
    assert "page.admin.write" in permission_ids

    username = f"zz_admin_api_{uuid4().hex[:10]}"
    initial_password = "abc12345"

    # 1) 创建用户
    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": initial_password,
            "permission_ids": [permission_ids["page.admin.read"]],
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
    assert "page.admin.read" in created["permissions"]

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

    # 3) 覆盖权限
    perms_resp = client.put(
        f"/admin/users/{user_id}/permissions",
        headers=headers,
        json={
            "permission_ids": [
                permission_ids["page.admin.read"],
                permission_ids["page.admin.write"],
            ]
        },
    )
    assert perms_resp.status_code == 200, perms_resp.text

    perms_user = perms_resp.json()
    assert "page.admin.read" in perms_user["permissions"]
    assert "page.admin.write" in perms_user["permissions"]

    # 4) 重置密码
    reset_resp = client.post(
        f"/admin/users/{user_id}/reset-password",
        headers=headers,
        json={},
    )
    assert reset_resp.status_code == 200, reset_resp.text

    reset_data = reset_resp.json()
    assert reset_data["ok"] is True

    # 5) 使用重置后的密码登录
    login_resp = client.post(
        "/users/login",
        json={"username": username, "password": "000000"},
    )
    assert login_resp.status_code == 200, login_resp.text
    assert "access_token" in login_resp.json()
