# tests/api/test_user_api.py
#
# 目标：
# - 验证运行时基础用户接口仍然可用：
#   - /users/login
#   - /users/me
# - 不再把管理员“用户列表”接口放在 /users/ 下面测试
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


def test_admin_can_get_me_and_permissions(client: TestClient) -> None:
    """
    admin 拿 token 后，访问 /users/me 成功，并能看到 page.admin.read / page.admin.write。
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

    assert isinstance(me, dict)
    assert {"id", "username", "permissions"} <= set(me.keys())
    assert isinstance(me["id"], int)
    assert isinstance(me["username"], str)
    assert isinstance(me["permissions"], list)

    perms = me["permissions"]
    assert "page.admin.read" in perms
    assert "page.admin.write" in perms
