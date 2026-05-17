# tests/api/test_wms_system_service_dependencies_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _dependency_by_code(dependencies: list[dict]) -> dict[str, dict]:
    return {str(item["dependency_code"]): item for item in dependencies}


def test_wms_system_service_dependencies_returns_declared_dependencies() -> None:
    client = TestClient(app)

    response = client.get("/system/read/v1/service-dependencies")

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["app_code"] == "wms"
    assert body["app_name"] == "仓储管理"
    assert body["source_service_client_code"] == "wms-service"

    dependencies = body["dependencies"]
    assert isinstance(dependencies, list)
    assert dependencies

    by_code = _dependency_by_code(dependencies)

    pms_projection = by_code["wms.depends_on.pms.projection_feed"]
    assert pms_projection["target_app_code"] == "pms"
    assert pms_projection["target_capability_code"] == "pms.read.projection_feed"
    assert pms_projection["required_permission_code"] == "pms.read.projection_feed"
    assert pms_projection["is_required"] is True
    assert pms_projection["is_active"] is True
    assert "PMS_API_BASE_URL" in pms_projection["required_config_keys"]

    pms_projection_paths = {
        (endpoint["http_method"], endpoint["path"])
        for endpoint in pms_projection["endpoints"]
    }
    assert ("GET", "/pms/read/v1/projection-feed/items") in pms_projection_paths
    assert ("GET", "/pms/read/v1/projection-feed/suppliers") in pms_projection_paths
    assert ("GET", "/pms/read/v1/projection-feed/uoms") in pms_projection_paths
    assert ("GET", "/pms/read/v1/projection-feed/sku-codes") in pms_projection_paths
    assert ("GET", "/pms/read/v1/projection-feed/barcodes") in pms_projection_paths

    oms = by_code["wms.depends_on.oms.fulfillment_ready_orders"]
    assert oms["target_app_code"] == "oms"
    assert oms["target_capability_code"] == "oms.read.fulfillment_ready_orders"
    assert "OMS_API_BASE_URL" in oms["required_config_keys"]
    assert {
        (endpoint["http_method"], endpoint["path"])
        for endpoint in oms["endpoints"]
    } == {("GET", "/oms/read/v1/fulfillment-ready-orders")}

    procurement = by_code["wms.depends_on.procurement.receiving_sources"]
    assert procurement["target_app_code"] == "procurement"
    assert procurement["target_capability_code"] == "procurement.read.wms_receiving_sources"
    assert "PROCUREMENT_API_BASE_URL" in procurement["required_config_keys"]

    procurement_paths = {
        (endpoint["http_method"], endpoint["path"])
        for endpoint in procurement["endpoints"]
    }
    assert ("GET", "/procurement/read/v1/wms/receiving-sources") in procurement_paths
    assert ("GET", "/procurement/read/v1/wms/receiving-sources/{po_id}") in procurement_paths

    logistics = by_code["wms.depends_on.logistics.shipping_record_facts"]
    assert logistics["target_app_code"] == "logistics"
    assert logistics["target_capability_code"] == "logistics.read.shipping_record_facts"
    assert "LOGISTICS_API_BASE_URL" in logistics["required_config_keys"]
    assert "LOGISTICS_API_TOKEN" in logistics["required_config_keys"]

    required_keys = {
        "dependency_code",
        "dependency_name",
        "target_app_code",
        "target_capability_code",
        "required_permission_code",
        "description",
        "is_required",
        "is_active",
        "required_config_keys",
        "source_modules",
        "endpoints",
    }
    for dependency in dependencies:
        assert required_keys <= set(dependency)
        assert dependency["required_permission_code"] == dependency["target_capability_code"]
        assert dependency["endpoints"]

        assert "approved" not in dependency
        assert "written" not in dependency
        assert "verified" not in dependency
        assert "granted" not in dependency


def test_wms_system_service_dependencies_includes_pms_runtime_read_dependencies() -> None:
    client = TestClient(app)

    response = client.get("/system/read/v1/service-dependencies")

    assert response.status_code == 200, response.text
    by_code = _dependency_by_code(response.json()["dependencies"])

    assert "wms.depends_on.pms.item_read" in by_code
    assert "wms.depends_on.pms.uom_read" in by_code
    assert "wms.depends_on.pms.barcode_read" in by_code
    assert "wms.depends_on.pms.sku_code_read" in by_code

    sku_code = by_code["wms.depends_on.pms.sku_code_read"]
    sku_code_paths = {
        (endpoint["http_method"], endpoint["path"])
        for endpoint in sku_code["endpoints"]
    }
    assert ("POST", "/pms/read/v1/sku-codes/query") in sku_code_paths
    assert ("GET", "/pms/read/v1/sku-codes/resolve-outbound-default") in sku_code_paths


def test_wms_system_service_dependencies_is_registered_in_openapi() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]

    assert "/system/read/v1/service-dependencies" in paths
    assert "get" in paths["/system/read/v1/service-dependencies"]
