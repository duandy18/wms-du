# tests/api/test_wms_system_page_catalog_api.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _page_by_code(pages: list[dict]) -> dict[str, dict]:
    return {str(page["page_code"]): page for page in pages}


def test_wms_system_page_catalog_returns_standard_catalog() -> None:
    client = TestClient(app)

    response = client.get("/system/read/v1/page-catalog")

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["app_code"] == "wms"
    assert body["app_name"] == "仓储管理"

    pages = body["pages"]
    assert isinstance(pages, list)
    assert pages

    by_code = _page_by_code(pages)

    root = by_code["wms"]
    assert root["page_code"] == "wms"
    assert root["page_name"] == "仓储管理"
    assert root["route_path"] is None
    assert root["parent_page_code"] is None
    assert root["level"] == 1
    assert root["read_permission_code"] == "page.wms.read"
    assert root["write_permission_code"] == "page.wms.write"
    assert root["is_active"] is True
    assert root["sort_order"] == 20
    assert root["source_updated_at"] is None

    inventory = by_code["wms.inventory"]
    assert inventory["page_name"] == "库存"
    assert inventory["parent_page_code"] == "wms"
    assert inventory["level"] == 2
    assert inventory["read_permission_code"] == "page.wms.read"
    assert inventory["write_permission_code"] == "page.wms.write"
    assert inventory["is_active"] is True

    main_inventory = by_code["wms.inventory.main"]
    assert main_inventory["page_name"] == "即时库存"
    assert main_inventory["route_path"] == "/inventory"
    assert main_inventory["parent_page_code"] == "wms.inventory"
    assert main_inventory["level"] == 3
    assert main_inventory["read_permission_code"] == "page.wms.read"
    assert main_inventory["write_permission_code"] == "page.wms.write"
    assert main_inventory["is_active"] is True
    assert main_inventory["sort_order"] == 10

    required_keys = {
        "page_code",
        "page_name",
        "route_path",
        "parent_page_code",
        "level",
        "read_permission_code",
        "write_permission_code",
        "is_active",
        "sort_order",
        "source_updated_at",
    }
    for page in pages:
        assert required_keys <= set(page.keys())


def test_wms_system_page_catalog_is_registered_in_openapi() -> None:
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200, response.text
    paths = response.json()["paths"]

    assert "/system/read/v1/page-catalog" in paths
    assert "get" in paths["/system/read/v1/page-catalog"]
