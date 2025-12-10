# tests/api/test_user_api.py
#
# 目标：
# - 验证 admin 用户可以：
#   - 登录
#   - 访问 /users/ 列表
#   - 访问 /users/me 并拿到 system.user.manage 权限
# - 仅通过 HTTP 调用，不直接写数据库。
#
# 前置要求：
# - 环境变量已指向 DEV 库，例如：
#     export WMS_DATABASE_URL=postgresql+psycopg://wms:wms@127.0.0.1:5433/wms
#     export WMS_TEST_DATABASE_URL=$WMS_DATABASE_URL
# - DEV 库中存在 admin 用户（可用 make dev-ensure-admin 创建），密码 admin123

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    使用 FastAPI TestClient 启动应用。

    注意：DB 连接由 alembic/env.py + WMS_DATABASE_URL 控制，
    本测试仅假设 env 已经正确指向 dev 库。
    """
    return TestClient(app)


def _ensure_env_dsn() -> None:
    """
    简单提示：如果环境变量没有设置，测试会失败。
    不在这里自动设置，避免和项目现有约定冲突。
    """
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


def test_admin_can_login_and_get_token(client: TestClient) -> None:
    """
    admin 可以成功登录，并拿到 access_token。
    """
    _ensure_env_dsn()

    resp = client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"


def test_admin_can_list_users(client: TestClient) -> None:
    """
    admin 拿 token 后，访问 /users/ 不应再 403。
    """
    _ensure_env_dsn()

    # 1) 登录拿 token
    login_resp = client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2) 访问 /users/ 列表
    list_resp = client.get("/users/", headers=headers)
    assert list_resp.status_code == 200, list_resp.text

    users = list_resp.json()
    assert isinstance(users, list)


def test_admin_permissions_contains_system_user_manage(client: TestClient) -> None:
    """
    admin 访问 /users/me，应当能看到 system.user.manage 在 permissions 列表中。
    """
    _ensure_env_dsn()

    login_resp = client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_resp = client.get("/users/me", headers=headers)
    assert me_resp.status_code == 200, me_resp.text
    me = me_resp.json()

    perms = me.get("permissions") or []
    assert isinstance(perms, list)
    assert "system.user.manage" in perms
