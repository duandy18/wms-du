# tests/api/test_admin_users_delete_api.py
#
# 目标：
# - 验证管理员可以删除未被业务单据引用的用户
# - 验证不能删除当前登录用户
#
# 说明：
# - 真正被业务单据引用的用户删除会受数据库外键约束影响
# - 这里不直接构造业务引用，只验证当前 delete API 的主链

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


def _find_row_by_username(rows: list[dict], username: str) -> dict | None:
    for row in rows:
        if row.get("username") == username:
            return row
    return None


def test_admin_can_delete_user(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    username = f"zz_admin_delete_{uuid4().hex[:10]}"

    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": "abc12345",
            "permission_ids": [],
            "full_name": "Delete Test",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    user_id = created["id"]

    delete_resp = client.post(
        f"/admin/users/{user_id}/delete",
        headers=headers,
    )
    assert delete_resp.status_code == 200, delete_resp.text

    matrix_resp = client.get("/admin/users/permission-matrix", headers=headers)
    assert matrix_resp.status_code == 200, matrix_resp.text
    data = matrix_resp.json()
    rows = data.get("rows")
    assert isinstance(rows, list)

    assert _find_row_by_username(rows, username) is None


def test_admin_cannot_delete_self(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    delete_resp = client.post(
        "/admin/users/1/delete",
        headers=headers,
    )
    assert delete_resp.status_code == 400, delete_resp.text
    assert "不能删除当前登录用户" in delete_resp.text
