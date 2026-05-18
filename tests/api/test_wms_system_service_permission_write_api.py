# tests/api/test_wms_system_service_permission_write_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

APPLY_PATH = "/system/write/v1/service-permissions/apply"
VERIFY_PATH = "/system/write/v1/service-permissions/verify"
ERP_HEADERS = {"X-Service-Client": "erp-service"}


def _apply_payload(
    *,
    client_code: str = "zz-erp-write-test-service",
    capability_code: str = "wms.read.warehouses",
    is_active: bool = True,
) -> dict:
    return {
        "client_code": client_code,
        "client_name": "ERP Write Test Service",
        "capability_code": capability_code,
        "description": "ERP 写入 WMS service permission 测试",
        "is_active": is_active,
    }


def test_wms_service_permission_apply_requires_erp_service_client_header() -> None:
    client = TestClient(app)

    response = client.post(APPLY_PATH, json=_apply_payload())

    assert response.status_code == 401
    assert "wms_service_client_required" in response.text


def test_wms_service_permission_apply_rejects_non_erp_service_client() -> None:
    client = TestClient(app)

    response = client.post(
        APPLY_PATH,
        headers={"X-Service-Client": "logistics-service"},
        json=_apply_payload(),
    )

    assert response.status_code == 403
    assert "wms_service_permission_write_denied" in response.text


def test_wms_service_permission_apply_and_verify_round_trip() -> None:
    client = TestClient(app)

    response = client.post(APPLY_PATH, headers=ERP_HEADERS, json=_apply_payload())

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["app_code"] == "wms"
    assert body["client_code"] == "zz-erp-write-test-service"
    assert body["client_name"] == "ERP Write Test Service"
    assert body["capability_code"] == "wms.read.warehouses"
    assert body["description"] == "ERP 写入 WMS service permission 测试"
    assert body["is_active"] is True
    assert body["applied"] is True
    assert body["verified"] is True
    assert body["permission_id"] > 0
    assert body["granted_at"]

    verify_response = client.get(
        VERIFY_PATH,
        headers=ERP_HEADERS,
        params={
            "client_code": "zz-erp-write-test-service",
            "capability_code": "wms.read.warehouses",
        },
    )

    assert verify_response.status_code == 200, verify_response.text
    verify_body = verify_response.json()

    assert verify_body["app_code"] == "wms"
    assert verify_body["client_code"] == "zz-erp-write-test-service"
    assert verify_body["capability_code"] == "wms.read.warehouses"
    assert verify_body["client_exists"] is True
    assert verify_body["capability_exists"] is True
    assert verify_body["permission_exists"] is True
    assert verify_body["client_is_active"] is True
    assert verify_body["capability_is_active"] is True
    assert verify_body["permission_is_active"] is True
    assert verify_body["verified"] is True


def test_wms_service_permission_apply_can_disable_permission_without_disabling_client() -> None:
    client = TestClient(app)

    response = client.post(
        APPLY_PATH,
        headers=ERP_HEADERS,
        json=_apply_payload(
            client_code="zz-erp-write-test-disable-service",
            capability_code="wms.read.warehouses",
            is_active=False,
        ),
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["client_code"] == "zz-erp-write-test-disable-service"
    assert body["is_active"] is False
    assert body["verified"] is False

    verify_response = client.get(
        VERIFY_PATH,
        headers=ERP_HEADERS,
        params={
            "client_code": "zz-erp-write-test-disable-service",
            "capability_code": "wms.read.warehouses",
        },
    )

    assert verify_response.status_code == 200, verify_response.text
    verify_body = verify_response.json()

    assert verify_body["client_is_active"] is True
    assert verify_body["permission_is_active"] is False
    assert verify_body["verified"] is False


def test_wms_service_permission_apply_rejects_unknown_capability() -> None:
    client = TestClient(app)

    response = client.post(
        APPLY_PATH,
        headers=ERP_HEADERS,
        json=_apply_payload(capability_code="wms.read.unknown_for_write_test"),
    )

    assert response.status_code == 404
    assert "wms_service_capability_not_found" in response.text


def test_wms_service_permission_verify_returns_false_for_missing_permission() -> None:
    client = TestClient(app)

    response = client.get(
        VERIFY_PATH,
        headers=ERP_HEADERS,
        params={
            "client_code": "zz-erp-write-test-missing-service",
            "capability_code": "wms.read.warehouses",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["client_exists"] is False
    assert body["capability_exists"] is True
    assert body["permission_exists"] is False
    assert body["verified"] is False


def test_wms_service_permission_write_routes_are_registered_in_openapi() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]

    assert APPLY_PATH in paths
    assert "post" in paths[APPLY_PATH]
    assert VERIFY_PATH in paths
    assert "get" in paths[VERIFY_PATH]
