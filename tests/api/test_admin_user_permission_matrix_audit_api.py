# tests/api/test_admin_user_permission_matrix_audit_api.py
#
# 目标：
# - 验证管理员保存 /admin/users/{user_id}/permission-matrix 后，
#   会写入一条 ADMIN_USER / PERMISSION_MATRIX_UPDATED 审计事件
# - 仅通过 HTTP 调用主链，不直接调用 service
#
# 副作用：
# - 会创建一个唯一用户名的测试用户（前缀 zz_admin_matrix_audit_）
# - 会往 audit_events 写入一条 ADMIN_USER 审计记录

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.db.session import SessionLocal


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


def _fetch_latest_admin_user_audit(ref: str) -> dict:
    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                SELECT
                  category,
                  ref,
                  meta
                FROM audit_events
                WHERE category = 'ADMIN_USER'
                  AND ref = :ref
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"ref": ref},
        ).mappings().first()

    if row is None:
        raise AssertionError(f"未找到 ADMIN_USER 审计事件: ref={ref}")

    return {
        "category": row["category"],
        "ref": row["ref"],
        "meta": row["meta"],
    }


def test_admin_save_permission_matrix_writes_audit_event(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)
    actor_user_id = _get_current_user_id(client, headers)

    username = f"zz_admin_matrix_audit_{uuid4().hex[:10]}"

    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": "abc12345",
            "permission_ids": [],
            "full_name": "Matrix Audit Test",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    user_id = created["id"]
    assert isinstance(user_id, int)

    page_codes = _get_matrix_page_codes(client, headers)
    assert "admin" in set(page_codes)

    pages = _build_empty_pages(page_codes)
    pages["admin"] = {"read": False, "write": True}

    save_resp = client.put(
        f"/admin/users/{user_id}/permission-matrix",
        headers=headers,
        json={
            "page_codes": page_codes,
            "pages": pages,
        },
    )
    assert save_resp.status_code == 200, save_resp.text

    audit = _fetch_latest_admin_user_audit(ref=f"USER:{user_id}")
    assert audit["category"] == "ADMIN_USER"
    assert audit["ref"] == f"USER:{user_id}"

    meta = audit["meta"]
    assert isinstance(meta, dict)
    assert meta["action"] == "PERMISSION_MATRIX_UPDATED"
    assert meta["actor_user_id"] == actor_user_id
    assert meta["target_user_id"] == user_id
    assert meta["target_username"] == username

    before_data = meta.get("before")
    after_data = meta.get("after")
    changed_pages = meta.get("changed_pages")

    assert isinstance(before_data, dict)
    assert isinstance(after_data, dict)
    assert isinstance(changed_pages, dict)

    assert before_data["user_id"] == user_id
    assert before_data["username"] == username
    assert after_data["user_id"] == user_id
    assert after_data["username"] == username

    assert before_data["pages"]["admin"]["write"] is False
    assert before_data["pages"]["admin"]["read"] is False

    assert after_data["pages"]["admin"]["write"] is True
    assert after_data["pages"]["admin"]["read"] is True

    assert changed_pages["admin"]["before"]["write"] is False
    assert changed_pages["admin"]["after"]["write"] is True
