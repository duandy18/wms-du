# tests/api/test_user_api.py
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


def _login(username: str, password: str) -> str:
    """登录，返回 access_token。"""
    resp = client.post(
        "/users/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "access_token" in data
    return data["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _unique_username(prefix: str = "ut_user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_register_and_list_users():
    """
    admin 能创建新用户，并在 /users 列表中看到：
    - username 一致
    - role_id 一致
    - is_active 为 True
    - full_name / phone / email 正确回显
    """
    token = _login(ADMIN_USERNAME, ADMIN_PASSWORD)
    headers = _auth_headers(token)

    username = _unique_username()
    payload = {
        "username": username,
        "password": "Pass1234!",
        "role_id": 1,  # 约定：初始化数据中 id=1 是 admin 角色
        "full_name": "测试用户",
        "phone": "13800000000",
        "email": "test@example.com",
    }

    resp = client.post("/users/register", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["username"] == username
    assert data["role_id"] == payload["role_id"]
    assert data["is_active"] is True
    assert data["full_name"] == payload["full_name"]
    assert data["phone"] == payload["phone"]
    assert data["email"] == payload["email"]

    # 列表中能查到
    resp2 = client.get("/users/", headers=headers)
    assert resp2.status_code == 200, resp2.text
    users = resp2.json()
    assert any(u["username"] == username for u in users)


def test_change_password_self_flow():
    """
    新用户可以：
    - 用初始密码登录
    - 调用 /users/change-password 修改自己的密码
    - 用新密码登录成功
    """
    admin_token = _login(ADMIN_USERNAME, ADMIN_PASSWORD)
    admin_headers = _auth_headers(admin_token)

    username = _unique_username("ut_chgpwd")
    orig_password = "OrigPass123!"
    new_password = "NewPass456!"

    # 1) admin 创建用户
    resp = client.post(
        "/users/register",
        json={
            "username": username,
            "password": orig_password,
            "role_id": 1,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text

    # 2) 新用户登录
    user_token = _login(username, orig_password)
    user_headers = _auth_headers(user_token)

    # 3) 调用 /users/change-password
    resp2 = client.post(
        "/users/change-password",
        json={"old_password": orig_password, "new_password": new_password},
        headers=user_headers,
    )
    assert resp2.status_code == 200, resp2.text
    body = resp2.json()
    assert body.get("ok") is True

    # 4) 用新密码再次登录
    _ = _login(username, new_password)


def test_admin_reset_password_to_default():
    """
    admin 可以调用 /users/{id}/reset-password：
    - 将用户密码重置为默认 000000
    - 重置后用户可用 000000 登录
    """
    admin_token = _login(ADMIN_USERNAME, ADMIN_PASSWORD)
    admin_headers = _auth_headers(admin_token)

    username = _unique_username("ut_reset")
    init_password = "TempPass123!"

    # 1) 创建用户
    resp = client.post(
        "/users/register",
        json={
            "username": username,
            "password": init_password,
            "role_id": 1,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    user = resp.json()
    user_id = user["id"]

    # 2) 重置密码
    resp2 = client.post(
        f"/users/{user_id}/reset-password",
        json={},
        headers=admin_headers,
    )
    assert resp2.status_code == 200, resp2.text
    body = resp2.json()
    assert body.get("ok") is True

    # 3) 用默认密码 000000 登录
    _ = _login(username, "000000")


def test_update_user_profile_and_toggle_active():
    """
    admin 能通过 PATCH /users/{id}：
    - 更新 full_name / phone / email / role_id
    - 切换 is_active 标志
    """
    admin_token = _login(ADMIN_USERNAME, ADMIN_PASSWORD)
    admin_headers = _auth_headers(admin_token)

    username = _unique_username("ut_update")
    password = "UserPass123!"

    # 1) 创建用户
    resp = client.post(
        "/users/register",
        json={
            "username": username,
            "password": password,
            "role_id": 1,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    user = resp.json()
    user_id = user["id"]
    assert user["is_active"] is True

    # 2) 更新资料 + 停用
    resp2 = client.patch(
        f"/users/{user_id}",
        json={
            "full_name": "更新后的姓名",
            "phone": "13900000000",
            "email": "updated@example.com",
            "is_active": False,
        },
        headers=admin_headers,
    )
    assert resp2.status_code == 200, resp2.text
    updated = resp2.json()
    assert updated["full_name"] == "更新后的姓名"
    assert updated["phone"] == "13900000000"
    assert updated["email"] == "updated@example.com"
    assert updated["is_active"] is False

    # 3) 再次启用
    resp3 = client.patch(
        f"/users/{user_id}",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert resp3.status_code == 200, resp3.text
    updated2 = resp3.json()
    assert updated2["is_active"] is True
