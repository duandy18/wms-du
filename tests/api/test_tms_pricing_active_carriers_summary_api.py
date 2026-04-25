# tests/api/test_tms_pricing_active_carriers_summary_api.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


async def login(client: AsyncClient) -> str:
    r = await client.post(
        "/users/login",
        json={
            "username": "admin",
            "password": "admin123",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _pick_first_warehouse_id(
    client: AsyncClient,
    headers: dict[str, str],
) -> int:
    r = await client.get("/warehouses", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()["data"] or []
    assert rows, "no warehouses"
    return int(rows[0]["id"])


async def _list_shipping_providers(
    client: AsyncClient,
    headers: dict[str, str],
) -> list[dict]:
    r = await client.get("/shipping-assist/pricing/providers", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()["data"] or []
    assert isinstance(rows, list), rows
    return rows


async def _list_warehouse_bindings(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    warehouse_id: int,
) -> list[dict]:
    r = await client.get(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    rows = r.json()["data"] or []
    assert isinstance(rows, list), rows
    return rows


async def _create_shipping_provider(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    code: str,
) -> int:
    r = await client.post(
        "/shipping-assist/pricing/providers",
        headers=headers,
        json={
            "name": name,
            "code": code,
            "active": True,
            "priority": 0,
            "pricing_model": None,
            "region_rules": None,
        },
    )
    assert r.status_code == 201, r.text
    return int(r.json()["data"]["id"])


async def _pick_unbound_provider_id(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    warehouse_id: int,
) -> int:
    providers = await _list_shipping_providers(client, headers)
    bindings = await _list_warehouse_bindings(client, headers, warehouse_id=warehouse_id)
    bound_provider_ids = {int(row["shipping_provider_id"]) for row in bindings}

    for row in providers:
        provider_id = int(row["id"])
        if provider_id not in bound_provider_ids:
            return provider_id

    suffix = int(datetime.now(timezone.utc).timestamp() * 1000) % 1_000_000
    return await _create_shipping_provider(
        client,
        headers,
        name=f"TEST-SUMMARY-PROVIDER-{suffix}",
        code=f"TSP{suffix}",
    )


async def _create_template(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    shipping_provider_id: int,
    name: str,
) -> int:
    r = await client.post(
        "/shipping-assist/pricing/templates",
        headers=headers,
        json={
            "shipping_provider_id": int(shipping_provider_id),
            "name": name,
            "expected_ranges_count": 1,
            "expected_groups_count": 1,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    return int(body["data"]["id"])


async def _put_ranges(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    template_id: int,
) -> int:
    r = await client.put(
        f"/shipping-assist/pricing/templates/{template_id}/ranges",
        headers=headers,
        json={
            "ranges": [
                {
                    "min_kg": 0,
                    "max_kg": None,
                    "sort_order": 0,
                    "default_pricing_mode": "flat",
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    return int(body["ranges"][0]["id"])


async def _post_group(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    template_id: int,
) -> int:
    r = await client.post(
        f"/shipping-assist/pricing/templates/{template_id}/groups",
        headers=headers,
        json={
            "sort_order": 0,
            "active": True,
            "provinces": [{"province_name": "北京市"}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    return int(body["group"]["id"])


async def _put_single_matrix_cell(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    template_id: int,
    group_id: int,
    range_id: int,
) -> None:
    r = await client.put(
        f"/shipping-assist/pricing/templates/{template_id}/matrix-cells",
        headers=headers,
        json={
            "cells": [
                {
                    "group_id": int(group_id),
                    "module_range_id": int(range_id),
                    "pricing_mode": "flat",
                    "flat_amount": 10,
                    "active": True,
                }
            ]
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert len(body["cells"]) == 1


async def _submit_validation(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    template_id: int,
) -> None:
    r = await client.post(
        f"/shipping-assist/pricing/templates/{template_id}/submit-validation",
        headers=headers,
        json={"confirm_validated": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["validation_status"] == "passed"


async def _bind_template(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    warehouse_id: int,
    shipping_provider_id: int,
    template_id: int,
):
    return await client.post(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings",
        headers=headers,
        json={
            "shipping_provider_id": int(shipping_provider_id),
            "active_template_id": int(template_id),
            "active": False,
            "priority": 0,
            "pickup_cutoff_time": "18:00",
            "remark": "active-carriers-summary-test",
        },
    )


async def _create_bindable_template_bundle(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
) -> tuple[int, int, int]:
    warehouse_id = await _pick_first_warehouse_id(client, headers)
    shipping_provider_id = await _pick_unbound_provider_id(
        client,
        headers,
        warehouse_id=warehouse_id,
    )
    template_id = await _create_template(
        client,
        headers,
        shipping_provider_id=shipping_provider_id,
        name=name,
    )
    range_id = await _put_ranges(client, headers, template_id=template_id)
    group_id = await _post_group(client, headers, template_id=template_id)
    await _put_single_matrix_cell(
        client,
        headers,
        template_id=template_id,
        group_id=group_id,
        range_id=range_id,
    )
    await _submit_validation(client, headers, template_id=template_id)
    return warehouse_id, shipping_provider_id, template_id


async def _fetch_summary(
    client: AsyncClient,
    headers: dict[str, str],
) -> list[dict]:
    r = await client.get(
        "/shipping-assist/pricing/warehouses/active-carriers/summary",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    rows = body["data"] or []
    assert isinstance(rows, list), rows
    return rows


def _find_warehouse_summary(rows: list[dict], warehouse_id: int) -> dict | None:
    for row in rows:
        if int(row["warehouse_id"]) == int(warehouse_id):
            return row
    return None


@pytest.mark.asyncio
async def test_scheduled_binding_not_in_active_carriers_summary(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_bindable_template_bundle(
        client,
        headers,
        name="active-carriers-summary-scheduled",
    )

    bind_resp = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )
    assert bind_resp.status_code == 201, bind_resp.text

    future_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    activate_resp = await client.post(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/activate",
        headers=headers,
        json={"effective_from": future_time},
    )
    assert activate_resp.status_code == 200, activate_resp.text

    rows = await _fetch_summary(client, headers)
    warehouse_summary = _find_warehouse_summary(rows, warehouse_id)
    if warehouse_summary is None:
        return

    provider_ids = {
        int(item["provider_id"]) for item in (warehouse_summary["active_carriers"] or [])
    }
    assert int(shipping_provider_id) not in provider_ids


@pytest.mark.asyncio
async def test_active_binding_appears_in_active_carriers_summary(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_bindable_template_bundle(
        client,
        headers,
        name="active-carriers-summary-active",
    )

    bind_resp = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )
    assert bind_resp.status_code == 201, bind_resp.text

    activate_resp = await client.post(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/activate",
        headers=headers,
        json={"effective_from": None},
    )
    assert activate_resp.status_code == 200, activate_resp.text

    rows = await _fetch_summary(client, headers)
    warehouse_summary = _find_warehouse_summary(rows, warehouse_id)
    assert warehouse_summary is not None, rows

    provider_ids = {
        int(item["provider_id"]) for item in (warehouse_summary["active_carriers"] or [])
    }
    assert int(shipping_provider_id) in provider_ids
