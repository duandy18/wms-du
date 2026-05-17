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

    assert body["app_code"] == "wms"
    assert body["app_name"] == "仓储管理"
    assert body["app_type"] == "business_system"
    assert body["status"] == "available"
    assert body["default_web_path"] == "/wms/"
    assert body["default_api_path"] == "/api/wms"
    assert body["local_web_url"] == "http://127.0.0.1:5173"
    assert body["local_api_url"] == "http://127.0.0.1:8000"
    assert body["health_url"] == "/healthz"
    assert body["db_health_url"] is None
    assert body["openapi_url"] == "/openapi.json"
    assert body["page_catalog_url"] == "/system/read/v1/page-catalog"
    assert body["service_capabilities_url"] == "/system/read/v1/service-capabilities"
    assert body["service_dependencies_url"] == "/system/read/v1/service-dependencies"
    assert body["version"] == "1.1.0"

    build_info = body["build_info"]
    assert isinstance(build_info, dict)
    assert isinstance(build_info["environment"], str)
    assert build_info["environment"]
    assert "git_sha" in build_info
    assert "build_time" in build_info

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
