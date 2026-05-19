# tests/api/test_wms_system_iam_write_api.py
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

APPLY_PATH = "/system/write/v1/iam/apply"
VERIFY_PATH = "/system/write/v1/iam/verify"
ERP_HEADER = {"X-Service-Client": "erp-service"}


def _payload(username: str) -> dict:
    return {
        "users": [
            {
                "username": username,
                "full_name": "ERP Managed User",
                "phone": "13900001111",
                "email": f"{username}@example.com",
                "is_active": True,
            }
        ],
        "user_permissions": [
            {
                "username": username,
                "permission_code": "page.wms.read",
                "is_active": True,
            },
            {
                "username": username,
                "permission_code": "page.inbound.read",
                "is_active": True,
            },
        ],
    }


def test_wms_iam_apply_requires_erp_service_client_header() -> None:
    client = TestClient(app)

    response = client.post(APPLY_PATH, json=_payload("zz_missing_header"))

    assert response.status_code == 401
    assert "wms_service_client_required" in response.text


def test_wms_iam_apply_rejects_non_erp_service_client() -> None:
    client = TestClient(app)

    response = client.post(
        APPLY_PATH,
        headers={"X-Service-Client": "logistics-service"},
        json=_payload("zz_wrong_header"),
    )

    assert response.status_code == 403
    assert "wms_service_permission_write_denied" in response.text


def test_wms_iam_apply_and_verify_desired_state() -> None:
    client = TestClient(app)
    username = f"zz_erp_iam_{uuid4().hex[:10]}"
    payload = _payload(username)

    verify_before = client.post(VERIFY_PATH, headers=ERP_HEADER, json=payload)
    assert verify_before.status_code == 200, verify_before.text
    assert verify_before.json()["verified"] is False
    assert username in verify_before.json()["missing_users"]

    apply_response = client.post(APPLY_PATH, headers=ERP_HEADER, json=payload)
    assert apply_response.status_code == 200, apply_response.text

    applied = apply_response.json()
    assert applied["app_code"] == "wms"
    assert applied["applied"] is True
    assert applied["verified"] is True
    assert applied["user_count"] == 1
    assert applied["desired_permission_count"] == 2
    assert applied["missing_users"] == []
    assert applied["missing_permission_codes"] == []
    assert applied["missing_user_permissions"] == []
    assert applied["extra_user_permissions"] == []

    verify_after = client.post(VERIFY_PATH, headers=ERP_HEADER, json=payload)
    assert verify_after.status_code == 200, verify_after.text
    assert verify_after.json()["verified"] is True


def test_wms_iam_apply_replaces_supplied_user_permissions() -> None:
    client = TestClient(app)
    username = f"zz_erp_iam_{uuid4().hex[:10]}"

    first_payload = _payload(username)
    first_response = client.post(APPLY_PATH, headers=ERP_HEADER, json=first_payload)
    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["verified"] is True

    second_payload = {
        "users": first_payload["users"],
        "user_permissions": [
            {
                "username": username,
                "permission_code": "page.wms.read",
                "is_active": True,
            }
        ],
    }
    second_response = client.post(APPLY_PATH, headers=ERP_HEADER, json=second_payload)
    assert second_response.status_code == 200, second_response.text
    assert second_response.json()["verified"] is True

    old_verify = client.post(VERIFY_PATH, headers=ERP_HEADER, json=first_payload)
    assert old_verify.status_code == 200, old_verify.text
    old_body = old_verify.json()
    assert old_body["verified"] is False
    assert {
        "username": username,
        "permission_code": "page.inbound.read",
    } in old_body["missing_user_permissions"]


def test_wms_iam_apply_rejects_unknown_permission_code() -> None:
    client = TestClient(app)
    username = f"zz_erp_iam_{uuid4().hex[:10]}"
    payload = {
        "users": [
            {
                "username": username,
                "is_active": True,
            }
        ],
        "user_permissions": [
            {
                "username": username,
                "permission_code": "page.not_exists.read",
                "is_active": True,
            }
        ],
    }

    response = client.post(APPLY_PATH, headers=ERP_HEADER, json=payload)

    assert response.status_code == 404
    assert "wms_iam_permission_not_found" in response.text


def test_wms_iam_routes_are_registered_in_openapi() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]
    assert APPLY_PATH in paths
    assert VERIFY_PATH in paths
    assert "post" in paths[APPLY_PATH]
    assert "post" in paths[VERIFY_PATH]
