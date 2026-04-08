# tests/api/test_admin_users_audit_api.py
#
# 目标：
# - 验证管理员停用/启用用户后，会写入一条 ADMIN_USER / USER_STATUS_UPDATED 审计事件
# - 验证管理员重置用户密码后，会写入一条 ADMIN_USER / PASSWORD_RESET 审计事件
# - 仅通过 HTTP 调用主链，不直接调用 service
#
# 副作用：
# - 会创建唯一用户名的测试用户（前缀 zz_admin_user_audit_）
# - 会往 audit_events 写入 ADMIN_USER 审计记录

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
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


def _fetch_admin_user_audit(ref: str, action: str) -> dict:
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
                  AND meta->>'action' = :action
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"ref": ref, "action": action},
        ).mappings().first()

    if row is None:
        raise AssertionError(f"未找到 ADMIN_USER 审计事件: ref={ref}, action={action}")

    return {
        "category": row["category"],
        "ref": row["ref"],
        "meta": row["meta"],
    }


def test_admin_update_user_status_writes_audit_event(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)
    actor_user_id = _get_current_user_id(client, headers)

    username = f"zz_admin_user_audit_{uuid4().hex[:10]}"

    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": "abc12345",
            "permission_ids": [],
            "full_name": "User Status Audit Test",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    user_id = created["id"]
    assert isinstance(user_id, int)

    update_resp = client.patch(
        f"/admin/users/{user_id}",
        headers=headers,
        json={
            "is_active": False,
        },
    )
    assert update_resp.status_code == 200, update_resp.text

    updated = update_resp.json()
    assert updated["id"] == user_id
    assert updated["is_active"] is False

    audit = _fetch_admin_user_audit(
        ref=f"USER:{user_id}",
        action="USER_STATUS_UPDATED",
    )
    assert audit["category"] == "ADMIN_USER"
    assert audit["ref"] == f"USER:{user_id}"

    meta = audit["meta"]
    assert isinstance(meta, dict)
    assert meta["action"] == "USER_STATUS_UPDATED"
    assert meta["actor_user_id"] == actor_user_id
    assert meta["target_user_id"] == user_id
    assert meta["target_username"] == username

    before_data = meta.get("before")
    after_data = meta.get("after")
    assert isinstance(before_data, dict)
    assert isinstance(after_data, dict)

    assert before_data["is_active"] is True
    assert after_data["is_active"] is False


def test_admin_reset_password_writes_audit_event(client: TestClient) -> None:
    _ensure_env_dsn()
    headers = _login_admin_headers(client)
    actor_user_id = _get_current_user_id(client, headers)

    username = f"zz_admin_user_audit_{uuid4().hex[:10]}"

    create_resp = client.post(
        "/admin/users",
        headers=headers,
        json={
            "username": username,
            "password": "abc12345",
            "permission_ids": [],
            "full_name": "Password Reset Audit Test",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    user_id = created["id"]
    assert isinstance(user_id, int)

    reset_resp = client.post(
        f"/admin/users/{user_id}/reset-password",
        headers=headers,
        json={},
    )
    assert reset_resp.status_code == 200, reset_resp.text

    data = reset_resp.json()
    assert data["ok"] is True

    audit = _fetch_admin_user_audit(
        ref=f"USER:{user_id}",
        action="PASSWORD_RESET",
    )
    assert audit["category"] == "ADMIN_USER"
    assert audit["ref"] == f"USER:{user_id}"

    meta = audit["meta"]
    assert isinstance(meta, dict)
    assert meta["action"] == "PASSWORD_RESET"
    assert meta["actor_user_id"] == actor_user_id
    assert meta["target_user_id"] == user_id
    assert meta["target_username"] == username
