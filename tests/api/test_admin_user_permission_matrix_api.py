# tests/api/test_admin_user_permission_matrix_api.py
#
# 目标：
# - 验证管理员可以读取 /admin/users/permission-matrix
# - 验证矩阵只按一级页面输出
# - 验证 read/write 布尔值映射正确
# - 仅通过 HTTP 调用，不直接写数据库
#
# 副作用：
# - 会创建一个唯一用户名的测试用户（前缀 zz_admin_matrix_）

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


def test_admin_can_get_user_permission_matrix(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)

    username = f"zz_admin_matrix_{uuid4().hex[:10]}"

    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": "abc12345",
            "permission_ids": [],
            "full_name": "Matrix API Test",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    user_id = created["id"]
    assert isinstance(user_id, int)

    page_codes = _get_matrix_page_codes(client, headers)
    assert "admin" in set(page_codes)

    pages_payload = _build_empty_pages(page_codes)
    pages_payload["admin"] = {"read": True, "write": False}

    save_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "page_codes": page_codes,
            "pages": pages_payload,
        },
    )
    assert save_resp.status_code == 200, save_resp.text

    matrix_resp = client.get("/admin/users/permission-matrix", headers=headers)
    assert matrix_resp.status_code == 200, matrix_resp.text

    data = matrix_resp.json()
    assert isinstance(data, dict)

    pages = data.get("pages")
    rows = data.get("rows")

    assert isinstance(pages, list)
    assert isinstance(rows, list)
    assert pages, "permission-matrix pages should not be empty"
    assert rows, "permission-matrix rows should not be empty"

    first_page = pages[0]
    assert isinstance(first_page, dict)
    assert {"page_code", "page_name", "sort_order"} <= set(first_page.keys())

    result_page_codes = [item["page_code"] for item in pages]
    assert "admin" in result_page_codes

    created_row = _find_row_by_username(rows, username)
    assert {"user_id", "username", "is_active", "pages"} <= set(created_row.keys())
    assert isinstance(created_row["pages"], dict)

    admin_cell = created_row["pages"].get("admin")
    assert isinstance(admin_cell, dict)
    assert admin_cell["read"] is True
    assert admin_cell["write"] is False

    for page_code in result_page_codes:
        cell = created_row["pages"].get(page_code)
        assert isinstance(cell, dict)
        assert isinstance(cell.get("read"), bool)
        assert isinstance(cell.get("write"), bool)
