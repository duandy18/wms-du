# tests/ci/test_pms_item_create_by_id_retired.py
from __future__ import annotations

import json
from pathlib import Path

from app.main import app
from app.pms.items.contracts import item as item_contract
from app.pms.items.services.item_service import ItemService


def test_pms_create_item_by_id_internal_compat_path_is_retired() -> None:
    """
    ItemCreateById 曾经是历史修复/兼容入口。

    终态：
    - 不挂路由；
    - 不保留 contract；
    - 不保留 ItemService facade 方法；
    - 不保留 maintenance service 文件；
    - barcode 写入只能走 /item-barcodes 或 owner aggregate。
    """
    assert not hasattr(item_contract, "ItemCreateById")
    assert not hasattr(ItemService, "create_item_by_id")
    assert not Path("app/pms/items/services/item_maintenance_service.py").exists()


def test_pms_create_item_by_id_route_and_openapi_surface_are_absent() -> None:
    forbidden_path_fragments = {
        "create-by-id",
        "create_item_by_id",
        "maintenance",
    }

    for route in app.routes:
        path = str(getattr(route, "path", ""))
        if not path.startswith("/items"):
            continue
        lowered = path.lower()
        assert not any(fragment in lowered for fragment in forbidden_path_fragments), path

    for openapi_path in [Path("openapi/_current.json"), Path("openapi/v1.json")]:
        spec = json.loads(openapi_path.read_text())
        schemas = spec.get("components", {}).get("schemas", {})
        assert "ItemCreateById" not in schemas

        paths = spec.get("paths", {})
        for path in paths:
            lowered = str(path).lower()
            assert not any(fragment in lowered for fragment in forbidden_path_fragments), (
                f"{openapi_path}:{path}"
            )
