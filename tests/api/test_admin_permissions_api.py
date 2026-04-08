# tests/api/test_admin_permissions_api.py
#
# 目标：
# - 验证管理员权限字典接口已经收口到 /admin/permissions
# - 仅通过 HTTP 调用，不直接写数据库
#
# 副作用：
# - 会创建一个唯一权限名（前缀 zz.test.permission.）

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


def test_admin_can_list_permissions_via_admin_permissions(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    resp = client.get("/admin/permissions", headers=headers)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert isinstance(data, list)
    assert data, "admin/permissions should not be empty"

    first = data[0]
    assert isinstance(first, dict)
    assert {"id", "name"} <= set(first.keys())


def test_admin_can_create_permission_via_admin_permissions(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    permission_name = f"zz.test.permission.{uuid4().hex[:12]}"

    create_resp = client.post(
        "/admin/permissions",
        headers=headers,
        json={"name": permission_name},
    )
    assert create_resp.status_code == 201, create_resp.text

    created = create_resp.json()
    assert created["name"] == permission_name
    permission_id = created["id"]
    assert isinstance(permission_id, int)

    get_resp = client.get(f"/admin/permissions/{permission_id}", headers=headers)
    assert get_resp.status_code == 200, get_resp.text

    fetched = get_resp.json()
    assert fetched["id"] == permission_id
    assert fetched["name"] == permission_name
