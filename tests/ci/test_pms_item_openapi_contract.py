# tests/ci/test_pms_item_openapi_contract.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.main import app


_FORBIDDEN_ITEM_WRITE_FIELDS = {
    "barcode",
    "primary_barcode",
    "weight_kg",
    "net_weight_kg",
    "uom",
    "unit",
    "has_shelf_life",
}

_OWNER_OUTPUT_COMPAT_FIELDS = {
    "barcode",
    "primary_barcode",
    "weight_kg",
}

_OPENAPI_FILES = [
    Path("openapi/_current.json"),
    Path("openapi/v1.json"),
]


def _schema_props(spec: dict[str, Any], name: str) -> set[str]:
    schema = spec.get("components", {}).get("schemas", {}).get(name)
    assert isinstance(schema, dict), f"missing schema: {name}"
    props = schema.get("properties")
    assert isinstance(props, dict), f"schema has no properties: {name}"
    return set(props)


def test_runtime_openapi_pms_item_write_contract_excludes_compat_fields() -> None:
    """
    运行时 OpenAPI 护栏：

    - ItemCreate / ItemUpdate 是写入合同，不得暴露 owner 兼容输出字段；
    - barcode / primary_barcode 的真相源是 item_barcodes；
    - weight_kg 的真相源是 base item_uoms.net_weight_kg；
    - ItemOut 暂时保留 owner 输出兼容字段。
    """
    spec = app.openapi()

    for schema_name in ("ItemCreate", "ItemUpdate"):
        props = _schema_props(spec, schema_name)
        leaked = _FORBIDDEN_ITEM_WRITE_FIELDS & props
        assert leaked == set(), f"{schema_name} leaked forbidden PMS compat write fields: {sorted(leaked)}"

    item_out_props = _schema_props(spec, "ItemOut")
    assert _OWNER_OUTPUT_COMPAT_FIELDS <= item_out_props


def test_static_openapi_pms_item_write_contract_matches_runtime_boundary() -> None:
    """
    静态 OpenAPI 护栏：

    防止 openapi/_current.json / openapi/v1.json 回潮旧合同，
    误导前端或外部调用方把 barcode / weight_kg 当作 /items 写入字段。
    """
    for path in _OPENAPI_FILES:
        spec = json.loads(path.read_text())

        for schema_name in ("ItemCreate", "ItemUpdate"):
            props = _schema_props(spec, schema_name)
            leaked = _FORBIDDEN_ITEM_WRITE_FIELDS & props
            assert leaked == set(), (
                f"{path}:{schema_name} leaked forbidden PMS compat write fields: {sorted(leaked)}"
            )

        item_out_props = _schema_props(spec, "ItemOut")
        assert _OWNER_OUTPUT_COMPAT_FIELDS <= item_out_props, (
            f"{path}:ItemOut must keep owner compat output fields during this governance phase"
        )


def test_runtime_openapi_pms_item_create_requires_manual_sku_and_update_keeps_sku_closed() -> None:
    """
    SKU 编码治理合同：

    - ItemCreate 必须显式输入 sku；
    - ItemUpdate 仍然不开放 sku 变更；
    - items.sku 是当前主 SKU 投影；
    - item_sku_codes 是商品编码治理真相表。
    """
    spec = app.openapi()

    create_schema = spec["components"]["schemas"]["ItemCreate"]
    update_schema = spec["components"]["schemas"]["ItemUpdate"]

    create_props = create_schema.get("properties") or {}
    update_props = update_schema.get("properties") or {}
    create_required = set(create_schema.get("required") or [])

    assert "sku" in create_props
    assert "sku" in create_required
    assert "sku" not in update_props


def test_runtime_openapi_exposes_item_sku_codes_owner_governance_routes() -> None:
    """
    SKU 多编码治理入口必须是独立 owner surface，
    不能通过 PATCH /items/{id} 偷开 sku 变更。
    """
    spec = app.openapi()
    paths = spec.get("paths") or {}

    assert "/items/{item_id}/sku-codes" in paths
    assert "get" in paths["/items/{item_id}/sku-codes"]
    assert "post" in paths["/items/{item_id}/sku-codes"]

    assert "/items/{item_id}/sku-codes/{code_id}/disable" in paths
    assert "post" in paths["/items/{item_id}/sku-codes/{code_id}/disable"]

    assert "/items/{item_id}/sku-codes/{code_id}/enable" in paths
    assert "post" in paths["/items/{item_id}/sku-codes/{code_id}/enable"]

    assert "/items/{item_id}/sku-codes/change-primary" in paths
    assert "post" in paths["/items/{item_id}/sku-codes/change-primary"]
