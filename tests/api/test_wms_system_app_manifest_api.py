# tests/api/test_wms_system_app_manifest_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_wms_api_service_name_is_wms_api() -> None:
    client = TestClient(app)

    root_response = client.get("/")
    assert root_response.status_code == 200, root_response.text
    assert root_response.json()["name"] == "wms-api"
    assert root_response.json()["version"] == "1.1.0"

    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200, openapi_response.text
    assert openapi_response.json()["info"]["title"] == "wms-api"
    assert openapi_response.json()["info"]["version"] == "1.1.0"


def test_wms_system_app_manifest_returns_self_description_defaults() -> None:
    client = TestClient(app)

    response = client.get("/system/read/v1/app-manifest")

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["manifest_contract_version"] == "2.0"
    assert body["generated_at"]

    app_info = body["app"]
    assert app_info["app_code"] == "wms"
    assert app_info["app_name"] == "WMS 仓储执行系统"
    assert app_info["app_type"] == "business_system"
    assert app_info["owner_domain"] == "warehouse_execution"
    assert app_info["status"] == "available"

    deployment = body["deployment"]
    assert deployment["env_code"] == "test"
    assert deployment["deployment_mode"] == "local"
    assert deployment["web_path"] == "/wms"
    assert deployment["api_path"] == "/api/wms"
    assert deployment["control_base_url"] == "http://127.0.0.1:8000"
    assert deployment["internal_api_base_url"] == "http://127.0.0.1:8000"
    assert deployment["public_web_url"] == "http://127.0.0.1:5173"

    service_identity = body["service_identity"]
    assert service_identity["service_client_code"] == "wms-service"
    assert service_identity["service_client_header"] == "X-Service-Client"

    control_endpoints = {row["code"]: row for row in body["control_endpoints"]}
    assert control_endpoints["app_manifest"]["path"] == "/system/read/v1/app-manifest"
    assert control_endpoints["page_catalog"]["path"] == "/system/read/v1/page-catalog"
    assert control_endpoints["service_capabilities"]["path"] == (
        "/system/read/v1/service-capabilities"
    )
    assert control_endpoints["service_dependencies"]["path"] == (
        "/system/read/v1/service-dependencies"
    )
    assert control_endpoints["openapi"]["path"] == "/openapi.json"
    assert control_endpoints["health"]["path"] == "/healthz"
    assert control_endpoints["db_health"]["path"] == "/health/db"

    write_endpoints = {row["code"]: row for row in body["write_endpoints"]}
    assert write_endpoints["iam_apply"]["method"] == "POST"
    assert write_endpoints["iam_apply"]["path"] == "/system/write/v1/iam/apply"
    assert write_endpoints["iam_verify"]["method"] == "POST"
    assert write_endpoints["iam_verify"]["path"] == "/system/write/v1/iam/verify"
    assert write_endpoints["service_permission_apply"]["path"] == (
        "/system/write/v1/service-permissions/apply"
    )
    assert write_endpoints["service_permission_verify"]["method"] == "GET"
    assert write_endpoints["service_permission_verify"]["path"] == (
        "/system/write/v1/service-permissions/verify"
    )

    security = body["security"]
    assert security["self_description_auth_policy"] == "internal_control_plane"
    assert security["write_auth_policy"] == "erp_service_client_required"
    assert security["required_write_caller"] == "erp-service"

    build = body["build"]
    assert build["app_version"] == "1.1.0"
    assert "git_sha" in build
    assert "image_tag" in build
    assert "build_time" in build

    assert "default_web_path" not in body
    assert "default_api_path" not in body
    assert "local_web_url" not in body
    assert "local_api_url" not in body
    assert "page_catalog_url" not in body
    assert "service_capabilities_url" not in body
    assert "service_dependencies_url" not in body
    assert "version" not in body
    assert "build_info" not in body
    assert "is_active" not in body
    assert "is_visible" not in body
    assert "is_published" not in body


def test_wms_system_app_manifest_is_registered_in_openapi() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]

    assert "/system/read/v1/app-manifest" in paths
    assert "get" in paths["/system/read/v1/app-manifest"]
    assert "/health/db" in paths
    assert "get" in paths["/health/db"]

    schemas = response.json()["components"]["schemas"]
    manifest_schema = schemas["WmsSystemAppManifestOut"]
    assert "manifest_contract_version" in manifest_schema["properties"]
    assert "app" in manifest_schema["properties"]
    assert "deployment" in manifest_schema["properties"]
    assert "service_identity" in manifest_schema["properties"]
    assert "control_endpoints" in manifest_schema["properties"]
    assert "write_endpoints" in manifest_schema["properties"]
    assert "security" in manifest_schema["properties"]
    assert "build" in manifest_schema["properties"]
