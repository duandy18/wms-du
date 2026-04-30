# tests/api/test_pms_item_attribute_common_other_seed_api.py
from __future__ import annotations

import httpx
import pytest


async def _headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _attribute_defs(client: httpx.AsyncClient, headers: dict[str, str], *, product_kind: str) -> list[dict]:
    r = await client.get(
        f"/pms/item-attribute-defs?product_kind={product_kind}&active_only=true",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert isinstance(data["data"], list)
    return data["data"]


async def _options(client: httpx.AsyncClient, headers: dict[str, str], *, attribute_def_id: int) -> list[dict]:
    r = await client.get(
        f"/pms/item-attribute-defs/{attribute_def_id}/options?active_only=true",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert isinstance(data["data"], list)
    return data["data"]


@pytest.mark.asyncio
async def test_common_item_attribute_templates_are_seeded(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)

    rows = await _attribute_defs(client, headers, product_kind="COMMON")
    by_code = {row["code"]: row for row in rows}

    assert {"ORIGIN", "MANUFACTURER", "SERIES", "REMARK"} <= set(by_code)

    for code in ("ORIGIN", "MANUFACTURER", "SERIES", "REMARK"):
        row = by_code[code]
        assert row["product_kind"] == "COMMON"
        assert row["value_type"] == "TEXT"
        assert row["selection_mode"] == "SINGLE"
        assert row["is_item_required"] is False
        assert row["is_sku_required"] is False
        assert row["is_sku_segment"] is False
        assert row["is_active"] is True


@pytest.mark.asyncio
async def test_other_item_attribute_templates_and_options_are_seeded(client: httpx.AsyncClient) -> None:
    headers = await _headers(client)

    rows = await _attribute_defs(client, headers, product_kind="OTHER")
    by_code = {row["code"]: row for row in rows}

    assert {"MODEL", "MATERIAL", "COLOR", "SIZE", "USAGE"} <= set(by_code)

    expected_defs = {
        "MODEL": ("OPTION", "SINGLE", True),
        "MATERIAL": ("OPTION", "MULTI", True),
        "COLOR": ("OPTION", "SINGLE", True),
        "SIZE": ("OPTION", "SINGLE", True),
        "USAGE": ("OPTION", "MULTI", False),
    }

    for code, (value_type, selection_mode, is_sku_segment) in expected_defs.items():
        row = by_code[code]
        assert row["product_kind"] == "OTHER"
        assert row["value_type"] == value_type
        assert row["selection_mode"] == selection_mode
        assert row["is_item_required"] is False
        assert row["is_sku_required"] is False
        assert row["is_sku_segment"] is is_sku_segment
        assert row["is_active"] is True

    material_options = await _options(client, headers, attribute_def_id=int(by_code["MATERIAL"]["id"]))
    material_codes = {row["option_code"] for row in material_options}
    assert {"PAPER", "PLASTIC", "METAL", "WOOD", "FABRIC", "OTHER"} <= material_codes

    color_options = await _options(client, headers, attribute_def_id=int(by_code["COLOR"]["id"]))
    color_codes = {row["option_code"] for row in color_options}
    assert {"BLACK", "WHITE", "RED", "BLUE", "GREEN", "MIXED", "OTHER"} <= color_codes

    usage_options = await _options(client, headers, attribute_def_id=int(by_code["USAGE"]["id"]))
    usage_codes = {row["option_code"] for row in usage_options}
    assert {"OFFICE", "HOME", "OUTDOOR", "PET", "CLEANING", "STORAGE", "TOOL", "OTHER"} <= usage_codes
