# tests/api/test_item_sku_codes_api.py
from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _sku(prefix: str = "UT-SKU-CODE") -> str:
    return f"{prefix}-{uuid4().hex[:8].upper()}"


async def _login_admin_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_item(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    *,
    sku: str | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "sku": sku or _sku(),
        "name": f"UT-SKU-CODE-ITEM-{uuid4().hex[:8].upper()}",
        "spec": "SPEC-A",
        "brand_id": 1,
        "category_id": 1,
        "enabled": True,
        "supplier_id": 1,
        "lot_source_policy": "SUPPLIER_ONLY",
        "expiry_policy": "NONE",
        "derivation_allowed": True,
        "uom_governance_enabled": False,
    }
    r = await client.post("/items", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_create_item_syncs_primary_sku_code(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    sku = _sku("UT-PRIMARY")
    created = await _create_item(client, headers, sku=sku)
    item_id = int(created["id"])

    r = await client.get(f"/items/{item_id}/sku-codes", headers=headers)
    assert r.status_code == 200, r.text
    codes = r.json()

    assert len(codes) == 1
    primary = codes[0]
    assert primary["item_id"] == item_id
    assert primary["code"] == sku
    assert primary["code_type"] == "PRIMARY"
    assert primary["is_primary"] is True
    assert primary["is_active"] is True

    db_count = await session.execute(
        text(
            """
            SELECT COUNT(*)
              FROM item_sku_codes
             WHERE item_id = :item_id
               AND code = :sku
               AND code_type = 'PRIMARY'
               AND is_primary = TRUE
               AND is_active = TRUE
            """
        ),
        {"item_id": item_id, "sku": sku},
    )
    assert int(db_count.scalar_one()) == 1


@pytest.mark.asyncio
async def test_alias_sku_code_can_resolve_item_then_disable_and_enable(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)
    created = await _create_item(client, headers, sku=_sku("UT-ALIAS-PRIMARY"))
    item_id = int(created["id"])

    alias = _sku("ut-alias").lower()
    r_create = await client.post(
        f"/items/{item_id}/sku-codes",
        json={"code": alias, "code_type": "ALIAS", "remark": "历史别名"},
        headers=headers,
    )
    assert r_create.status_code == 201, r_create.text
    alias_row = r_create.json()
    assert alias_row["code"] == alias.upper()
    assert alias_row["code_type"] == "ALIAS"
    assert alias_row["is_primary"] is False
    assert alias_row["is_active"] is True

    r_by_alias = await client.get(f"/items/sku/{alias}", headers=headers)
    assert r_by_alias.status_code == 200, r_by_alias.text
    assert int(r_by_alias.json()["id"]) == item_id

    r_disable = await client.post(
        f"/items/{item_id}/sku-codes/{int(alias_row['id'])}/disable",
        headers=headers,
    )
    assert r_disable.status_code == 200, r_disable.text
    assert r_disable.json()["is_active"] is False

    r_disabled_lookup = await client.get(f"/items/sku/{alias}", headers=headers)
    assert r_disabled_lookup.status_code == 404, r_disabled_lookup.text

    r_enable = await client.post(
        f"/items/{item_id}/sku-codes/{int(alias_row['id'])}/enable",
        headers=headers,
    )
    assert r_enable.status_code == 200, r_enable.text
    assert r_enable.json()["is_active"] is True

    r_enabled_lookup = await client.get(f"/items/sku/{alias}", headers=headers)
    assert r_enabled_lookup.status_code == 200, r_enabled_lookup.text
    assert int(r_enabled_lookup.json()["id"]) == item_id


@pytest.mark.asyncio
async def test_change_primary_keeps_old_sku_as_alias_and_updates_items_projection(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    old_sku = _sku("UT-OLD")
    new_sku = _sku("UT-NEW")

    created = await _create_item(client, headers, sku=old_sku)
    item_id = int(created["id"])

    r_change = await client.post(
        f"/items/{item_id}/sku-codes/change-primary",
        json={"code": new_sku, "remark": "规则调整"},
        headers=headers,
    )
    assert r_change.status_code == 200, r_change.text
    primary = r_change.json()
    assert primary["code"] == new_sku
    assert primary["code_type"] == "PRIMARY"
    assert primary["is_primary"] is True
    assert primary["is_active"] is True

    r_get = await client.get(f"/items/{item_id}", headers=headers)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["sku"] == new_sku

    r_old = await client.get(f"/items/sku/{old_sku}", headers=headers)
    assert r_old.status_code == 200, r_old.text
    assert int(r_old.json()["id"]) == item_id

    r_new = await client.get(f"/items/sku/{new_sku}", headers=headers)
    assert r_new.status_code == 200, r_new.text
    assert int(r_new.json()["id"]) == item_id

    rows = (
        await session.execute(
            text(
                """
                SELECT code, code_type, is_primary, is_active
                  FROM item_sku_codes
                 WHERE item_id = :item_id
                 ORDER BY is_primary DESC, code ASC
                """
            ),
            {"item_id": item_id},
        )
    ).mappings().all()

    by_code = {str(r["code"]): r for r in rows}
    assert by_code[new_sku]["code_type"] == "PRIMARY"
    assert bool(by_code[new_sku]["is_primary"]) is True
    assert by_code[old_sku]["code_type"] == "ALIAS"
    assert bool(by_code[old_sku]["is_primary"]) is False
    assert bool(by_code[old_sku]["is_active"]) is True


@pytest.mark.asyncio
async def test_primary_sku_code_cannot_be_disabled(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)
    created = await _create_item(client, headers, sku=_sku("UT-NO-DISABLE"))
    item_id = int(created["id"])

    r_list = await client.get(f"/items/{item_id}/sku-codes", headers=headers)
    assert r_list.status_code == 200, r_list.text
    primary = next(x for x in r_list.json() if x["is_primary"] is True)

    r_disable = await client.post(
        f"/items/{item_id}/sku-codes/{int(primary['id'])}/disable",
        headers=headers,
    )
    assert r_disable.status_code == 400, r_disable.text
    assert "primary sku code cannot be disabled" in r_disable.text


@pytest.mark.asyncio
async def test_create_item_aggregate_syncs_primary_sku_code(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)
    suffix = uuid4().hex[:8].upper()
    sku = f"UT-AGG-SKU-CODE-{suffix}"

    payload = {
        "item": {
            "sku": sku,
            "name": f"UT-AGG-SKU-CODE-ITEM-{suffix}",
            "spec": "500g",
            "brand_id": 1,
            "category_id": 1,
            "enabled": True,
            "supplier_id": 1,
            "lot_source_policy": "SUPPLIER_ONLY",
            "expiry_policy": "NONE",
            "derivation_allowed": True,
            "uom_governance_enabled": True,
            "shelf_life_value": None,
            "shelf_life_unit": None,
        },
        "uoms": [
            {
                "id": None,
                "uom_key": "BASE",
                "uom": "PCS",
                "ratio_to_base": 1,
                "display_name": "PCS",
                "net_weight_kg": None,
                "is_base": True,
                "is_purchase_default": True,
                "is_inbound_default": True,
                "is_outbound_default": True,
            }
        ],
        "barcodes": [],
    }

    r = await client.post("/items/aggregate", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    item_id = int(r.json()["item"]["id"])

    r_codes = await client.get(f"/items/{item_id}/sku-codes", headers=headers)
    assert r_codes.status_code == 200, r_codes.text
    codes = r_codes.json()

    assert len(codes) == 1
    assert codes[0]["code"] == sku
    assert codes[0]["code_type"] == "PRIMARY"
    assert codes[0]["is_primary"] is True
    assert codes[0]["is_active"] is True
