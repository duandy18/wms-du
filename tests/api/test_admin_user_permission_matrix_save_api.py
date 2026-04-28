# tests/api/test_admin_user_permission_matrix_save_api.py
#
# 目标：
# - 验证管理员可以保存 /admin/users/{user_id}/permission-matrix
# - 验证 write=true 会自动补 read=true
# - 验证保存时只接管一级页面 page 权限，不破坏矩阵返回结构
# - 验证旧前端列集落后时会被拒绝
# - 验证当前登录用户不能移除自己的 admin.write
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

    page_codes = _get_matrix_page_codes(client, headers)
    assert {"admin", "wms", "oms", "shipping_assist", "finance", "pms"} <= set(page_codes)

    pages = _build_empty_pages(page_codes)
    pages["wms"] = {"read": False, "write": True}
    pages["admin"] = {"read": True, "write": False}

    save_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "page_codes": page_codes,
            "pages": pages,
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

    page_codes = _get_matrix_page_codes(client, headers)
    pages = _build_empty_pages(page_codes)
    pages["unknown_domain"] = {"read": True, "write": False}

    save_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "page_codes": page_codes,
            "pages": pages,
        },
    )
    assert save_resp.status_code == 400, save_resp.text
    assert "非法一级页面" in save_resp.text


def test_admin_save_user_permission_matrix_rejects_stale_page_codes(
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

    page_codes = _get_matrix_page_codes(client, headers)
    assert len(page_codes) >= 1

    stale_page_codes = page_codes[:-1]
    pages = _build_empty_pages(stale_page_codes)

    save_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "page_codes": stale_page_codes,
            "pages": pages,
        },
    )
    assert save_resp.status_code == 400, save_resp.text
    assert "矩阵列已过期" in save_resp.text


def test_admin_cannot_remove_own_admin_write_via_matrix(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    current_user_id = _get_current_user_id(client, headers)
    page_codes = _get_matrix_page_codes(client, headers)
    pages = _build_empty_pages(page_codes)

    save_resp = client.put(
        f"/admin/users/{current_user_id}/permission-matrix",
        headers=headers,
        json={
            "page_codes": page_codes,
            "pages": pages,
        },
    )
    assert save_resp.status_code == 400, save_resp.text
    assert "不能移除当前登录用户自己的 page.admin.write" in save_resp.text
