# tests/api/test_admin_users_delete_api.py
#
# 目标：
# - 验证管理员可以删除未被业务单据引用的用户
# - 验证不能删除当前登录用户
# - 验证不能删除最后一个仍拥有 page.admin.write 的有效用户
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


def _find_row_by_username(rows: list[dict], username: str) -> dict | None:
    for row in rows:
        if row.get("username") == username:
            return row
    return None


def _get_current_user_id(
    client: TestClient,
    headers: dict[str, str],
) -> int:
    resp = client.get("/users/me", headers=headers)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    user_id = data.get("id")
    assert isinstance(user_id, int)
    return user_id


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
    current_user_id = _get_current_user_id(client, headers)

    delete_resp = client.post(
        f"/admin/users/{current_user_id}/delete",
        headers=headers,
    )
    assert delete_resp.status_code == 400, delete_resp.text
    assert "不能删除当前登录用户" in delete_resp.text


def test_admin_cannot_delete_last_admin_write_user(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            "full_name": "Delete Admin Guard Test",
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

    delete_resp = client.post(
        f"/admin/users/{user_id}/delete",
        headers=headers,
    )
    assert delete_resp.status_code == 400, delete_resp.text
    assert "不能删除最后一个仍拥有 page.admin.write 的有效用户" in delete_resp.text

    matrix_resp = client.get("/admin/users/permission-matrix", headers=headers)
    assert matrix_resp.status_code == 200, matrix_resp.text
    data = matrix_resp.json()
    rows = data.get("rows")
    assert isinstance(rows, list)
    assert _find_row_by_username(rows, username) is not None
