# tests/api/test_admin_users_api.py
#
# 目标：
# - 验证管理员用户管理接口已经收口到 /admin/users
# - 验证授权调整通过 /admin/users/{user_id}/permission-matrix 完成
# - 验证不能停用最后一个仍拥有 page.admin.write 的有效用户
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
from app.user.repositories.user_repository import UserRepository


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


def _get_matrix_page_codes(
    client: TestClient,
    headers: dict[str, str],
) -> list[str]:
    resp = client.get("/admin/users/permission-matrix", headers=headers)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    pages = data.get("pages")
    assert isinstance(pages, list)

    page_codes = [item["page_code"] for item in pages]
    assert page_codes, "permission-matrix page_codes should not be empty"
    return page_codes


def _build_empty_pages(page_codes: list[str]) -> dict[str, dict[str, bool]]:
    return {
        code: {"read": False, "write": False}
        for code in page_codes
    }


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
    page_codes = _get_matrix_page_codes(client, headers)
    assert "admin" in set(page_codes)

    pages = _build_empty_pages(page_codes)
    pages["admin"] = {"read": False, "write": True}

    matrix_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "page_codes": page_codes,
            "pages": pages,
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


def test_admin_cannot_disable_last_admin_write_user(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    username = f"zz_admin_api_{uuid4().hex[:10]}"

    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": "abc12345",
            "permission_ids": [],
            "full_name": "Admin Disable Guard Test",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    user_id = created["id"]

    page_codes = _get_matrix_page_codes(client, headers)
    assert "admin" in set(page_codes)

    pages = _build_empty_pages(page_codes)
    pages["admin"] = {"read": True, "write": True}

    grant_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "page_codes": page_codes,
            "pages": pages,
        },
    )
    assert grant_resp.status_code == 200, grant_resp.text

    def fake_count_active_users_with_permission(self, permission_name: str) -> int:
        assert permission_name == "page.admin.write"
        return 1

    monkeypatch.setattr(
        UserRepository,
        "count_active_users_with_permission",
        fake_count_active_users_with_permission,
    )

    disable_resp = client.patch(
        f"/admin/users/{user_id}",
        headers=headers,
        json={"is_active": False},
    )
    assert disable_resp.status_code == 400, disable_resp.text
    assert "不能停用最后一个仍拥有 page.admin.write 的有效用户" in disable_resp.text

    users_resp = client.get("/admin/users", headers=headers)
    assert users_resp.status_code == 200, users_resp.text
    users = users_resp.json()
    saved_user = _find_user_by_username(users, username)
    assert saved_user["is_active"] is True
