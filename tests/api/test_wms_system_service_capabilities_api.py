# tests/api/test_wms_system_service_capabilities_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _capability_by_code(capabilities: list[dict]) -> dict[str, dict]:
    return {str(item["capability_code"]): item for item in capabilities}


def test_wms_system_service_capabilities_returns_declared_capabilities() -> None:
    client = TestClient(app)

    response = client.get("/system/read/v1/service-capabilities")

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["app_code"] == "wms"
    assert body["app_name"] == "仓储管理"

    capabilities = body["capabilities"]
    assert isinstance(capabilities, list)
    assert capabilities

    by_code = _capability_by_code(capabilities)

    warehouses = by_code["wms.read.warehouses"]
    assert warehouses["capability_code"] == "wms.read.warehouses"
    assert warehouses["capability_name"] == "Read WMS warehouses"
    assert warehouses["resource_code"] == "warehouses"
    assert warehouses["permission_code"] == "wms.read.warehouses"
    assert warehouses["description"] == "读取 WMS 仓库基础下拉能力"
    assert warehouses["is_active"] is True
    assert warehouses["source_updated_at"] is not None

    routes = warehouses["routes"]
    assert isinstance(routes, list)
    route_pairs = {(route["http_method"], route["path"]) for route in routes}
    assert ("GET", "/wms/read/v1/warehouses") in route_pairs
    assert ("GET", "/wms/read/v1/warehouses/{warehouse_id}") in route_pairs

    for route in routes:
        assert {"http_method", "path", "route_name", "auth_required", "is_active", "source_created_at"} <= set(route)
        assert route["auth_required"] is True
        assert route["is_active"] is True
        assert route["source_created_at"] is not None

    required_capability_keys = {
        "capability_code",
        "capability_name",
        "resource_code",
        "permission_code",
        "description",
        "is_active",
        "source_updated_at",
        "routes",
    }
    for capability in capabilities:
        assert required_capability_keys <= set(capability)
        assert capability["permission_code"] == capability["capability_code"]

    assert "approved" not in warehouses
    assert "written" not in warehouses
    assert "verified" not in warehouses


def test_wms_system_service_capabilities_include_write_capabilities() -> None:
    client = TestClient(app)

    response = client.get("/system/read/v1/service-capabilities")

    assert response.status_code == 200, response.text
    by_code = _capability_by_code(response.json()["capabilities"])

    assert "wms.write.shipping_handoff_import_results" in by_code
    assert "wms.write.shipping_handoff_shipping_results" in by_code

    import_result = by_code["wms.write.shipping_handoff_import_results"]
    route_pairs = {(route["http_method"], route["path"]) for route in import_result["routes"]}

    assert ("POST", "/shipping-assist/handoffs/import-results") in route_pairs


def test_wms_system_service_capabilities_is_registered_in_openapi() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]

    assert "/system/read/v1/service-capabilities" in paths
    assert "get" in paths["/system/read/v1/service-capabilities"]
