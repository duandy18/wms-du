# tests/api/test_tms_pricing_bindings_runtime_api.py
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
            "shipping_provider_code": code,
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
        name=f"TEST-RUNTIME-PROVIDER-{suffix}",
        code=f"TRP{suffix}",
    )


async def _create_template(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    shipping_provider_id: int,
    name: str,
    expected_ranges_count: int = 1,
    expected_groups_count: int = 1,
) -> int:
    r = await client.post(
        "/shipping-assist/pricing/templates",
        headers=headers,
        json={
            "shipping_provider_id": int(shipping_provider_id),
            "name": name,
            "expected_ranges_count": int(expected_ranges_count),
            "expected_groups_count": int(expected_groups_count),
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
    template_id: int | None,
    active: bool = False,
):
    payload = {
        "shipping_provider_id": int(shipping_provider_id),
        "active": bool(active),
        "priority": 0,
        "pickup_cutoff_time": "18:00",
        "remark": "binding-runtime-api-test",
    }
    if template_id is not None:
        payload["active_template_id"] = int(template_id)

    return await client.post(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings",
        headers=headers,
        json=payload,
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
    range_id = await _put_ranges(
        client,
        headers,
        template_id=template_id,
    )
    group_id = await _post_group(
        client,
        headers,
        template_id=template_id,
    )
    await _put_single_matrix_cell(
        client,
        headers,
        template_id=template_id,
        group_id=group_id,
        range_id=range_id,
    )
    await _submit_validation(
        client,
        headers,
        template_id=template_id,
    )
    return warehouse_id, shipping_provider_id, template_id


@pytest.mark.asyncio
async def test_activate_binding_immediately_returns_active_runtime_status(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_bindable_template_bundle(
        client,
        headers,
        name="runtime-activate-now",
    )

    bind_resp = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
        active=False,
    )
    assert bind_resp.status_code == 201, bind_resp.text

    activate_resp = await client.post(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/activate",
        headers=headers,
        json={"effective_from": None},
    )
    assert activate_resp.status_code == 200, activate_resp.text
    body = activate_resp.json()
    assert body["ok"] is True
    assert body["data"]["runtime_status"] == "active"
    assert body["data"]["active"] is True
    assert body["data"]["effective_from"] is not None
    assert body["data"]["disabled_at"] is None


@pytest.mark.asyncio
async def test_activate_binding_in_future_returns_scheduled_runtime_status(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_bindable_template_bundle(
        client,
        headers,
        name="runtime-activate-future",
    )

    bind_resp = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
        active=False,
    )
    assert bind_resp.status_code == 201, bind_resp.text

    future_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    activate_resp = await client.post(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/activate",
        headers=headers,
        json={"effective_from": future_time},
    )
    assert activate_resp.status_code == 200, activate_resp.text
    body = activate_resp.json()
    assert body["ok"] is True
    assert body["data"]["runtime_status"] == "scheduled"
    assert body["data"]["active"] is True
    assert body["data"]["effective_from"] is not None
    assert body["data"]["disabled_at"] is None


@pytest.mark.asyncio
async def test_deactivate_binding_returns_binding_disabled_runtime_status(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_bindable_template_bundle(
        client,
        headers,
        name="runtime-deactivate",
    )

    bind_resp = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
        active=True,
    )
    assert bind_resp.status_code == 201, bind_resp.text

    deactivate_resp = await client.post(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/deactivate",
        headers=headers,
        json={},
    )
    assert deactivate_resp.status_code == 200, deactivate_resp.text
    body = deactivate_resp.json()
    assert body["ok"] is True
    assert body["data"]["runtime_status"] == "binding_disabled"
    assert body["data"]["active"] is False
    assert body["data"]["disabled_at"] is not None


@pytest.mark.asyncio
async def test_activate_binding_without_template_returns_409(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id = await _pick_first_warehouse_id(client, headers)
    shipping_provider_id = await _pick_unbound_provider_id(
        client,
        headers,
        warehouse_id=warehouse_id,
    )

    bind_resp = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=None,
        active=False,
    )
    assert bind_resp.status_code == 201, bind_resp.text

    activate_resp = await client.post(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/activate",
        headers=headers,
        json={"effective_from": None},
    )
    assert activate_resp.status_code == 409, activate_resp.text
    assert "active_template_id required before activation" in activate_resp.text
