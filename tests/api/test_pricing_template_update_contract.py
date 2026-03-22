from __future__ import annotations

import time

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


async def _create_template(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    shipping_provider_id: int = 1,
    name: str = "template-update-contract",
    expected_ranges_count: int = 1,
    expected_groups_count: int = 1,
) -> dict:
    r = await client.post(
        "/tms/pricing/templates",
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
    assert body["data"]["status"] == "draft"
    assert body["data"]["expected_ranges_count"] == int(expected_ranges_count)
    assert body["data"]["expected_groups_count"] == int(expected_groups_count)
    assert body["data"]["expected_matrix_cells_count"] == int(expected_ranges_count) * int(
        expected_groups_count
    )
    return body["data"]


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
    r = await client.get("/shipping-providers", headers=headers)
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
        f"/tms/pricing/warehouses/{warehouse_id}/bindings",
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
        "/shipping-providers",
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
    body = r.json()
    return int(body["data"]["id"])


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

    suffix = int(time.time() * 1000) % 1_000_000
    return await _create_shipping_provider(
        client,
        headers,
        name=f"TEST-PROVIDER-{suffix}",
        code=f"TP{suffix}",
    )


async def _build_template_resources(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    template_id: int,
) -> None:
    ranges = [
        {
            "min_kg": 0,
            "max_kg": None,
            "sort_order": 0,
            "default_pricing_mode": "flat",
        }
    ]

    r1 = await client.put(
        f"/tms/pricing/templates/{template_id}/ranges",
        headers=headers,
        json={"ranges": ranges},
    )
    assert r1.status_code == 200, r1.text
    range_id = int(r1.json()["ranges"][0]["id"])

    r2 = await client.post(
        f"/tms/pricing/templates/{template_id}/groups",
        headers=headers,
        json={
            "sort_order": 0,
            "active": True,
            "provinces": [{"province_name": "北京市"}],
        },
    )
    assert r2.status_code == 200, r2.text
    group_id = int(r2.json()["group"]["id"])

    r3 = await client.put(
        f"/tms/pricing/templates/{template_id}/matrix-cells",
        headers=headers,
        json={
            "cells": [
                {
                    "group_id": group_id,
                    "module_range_id": range_id,
                    "pricing_mode": "flat",
                    "flat_amount": 10,
                    "active": True,
                }
            ]
        },
    )
    assert r3.status_code == 200, r3.text


async def _submit_template_validation(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    template_id: int,
) -> dict:
    r = await client.post(
        f"/tms/pricing/templates/{template_id}/submit-validation",
        headers=headers,
        json={"confirm_validated": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["validation_status"] == "passed"
    return body["data"]


async def _bind_template_to_warehouse(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    warehouse_id: int,
    shipping_provider_id: int,
    template_id: int,
) -> dict:
    r = await client.post(
        f"/tms/pricing/warehouses/{warehouse_id}/bindings",
        headers=headers,
        json={
            "shipping_provider_id": int(shipping_provider_id),
            "active_template_id": int(template_id),
            "active": True,
            "priority": 0,
            "pickup_cutoff_time": "18:00",
            "remark": "template-update-contract-bind",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    assert int(body["data"]["active_template_id"]) == int(template_id)
    return body["data"]


async def _create_bindable_template(
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

    created = await _create_template(
        client,
        headers,
        shipping_provider_id=shipping_provider_id,
        name=name,
        expected_ranges_count=1,
        expected_groups_count=1,
    )
    template_id = int(created["id"])

    await _build_template_resources(
        client,
        headers,
        template_id=template_id,
    )
    await _submit_template_validation(
        client,
        headers,
        template_id=template_id,
    )

    return warehouse_id, shipping_provider_id, template_id


@pytest.mark.asyncio
async def test_template_create_requires_expected_counts(client: AsyncClient) -> None:
    token = await login(client)
    headers = auth_headers(token)

    r = await client.post(
        "/tms/pricing/templates",
        headers=headers,
        json={
            "shipping_provider_id": 1,
            "name": "missing-expected-counts",
        },
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_template_update_rejects_active_status(client: AsyncClient) -> None:
    token = await login(client)
    headers = auth_headers(token)

    created = await _create_template(client, headers, name="reject-active-status")
    template_id = int(created["id"])

    r = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"status": "active"},
    )
    assert r.status_code == 422, r.text
    assert "draft / archived" in r.text


@pytest.mark.asyncio
async def test_template_can_archive_then_restore_to_draft(client: AsyncClient) -> None:
    token = await login(client)
    headers = auth_headers(token)

    created = await _create_template(client, headers, name="archive-restore")
    template_id = int(created["id"])

    r1 = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"status": "archived"},
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["ok"] is True
    assert body1["data"]["status"] == "archived"
    assert body1["data"]["archived_at"] is not None

    r2 = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"status": "draft"},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["ok"] is True
    assert body2["data"]["status"] == "draft"
    assert body2["data"]["archived_at"] is None


@pytest.mark.asyncio
async def test_archived_template_cannot_modify_assets_directly(client: AsyncClient) -> None:
    token = await login(client)
    headers = auth_headers(token)

    created = await _create_template(client, headers, name="archived-cannot-edit")
    template_id = int(created["id"])

    r1 = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"status": "archived"},
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"name": "should-fail-when-archived"},
    )
    assert r2.status_code == 400, r2.text
    assert "Only draft template can be modified" in r2.text


@pytest.mark.asyncio
async def test_restored_template_can_modify_assets_again(client: AsyncClient) -> None:
    token = await login(client)
    headers = auth_headers(token)

    created = await _create_template(client, headers, name="restore-then-edit")
    template_id = int(created["id"])

    r1 = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"status": "archived"},
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"status": "draft"},
    )
    assert r2.status_code == 200, r2.text

    r3 = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"name": "restored-template-new-name"},
    )
    assert r3.status_code == 200, r3.text
    body3 = r3.json()
    assert body3["ok"] is True
    assert body3["data"]["status"] == "draft"
    assert body3["data"]["name"] == "restored-template-new-name"
    assert body3["data"]["archived_at"] is None
    assert body3["data"]["validation_status"] == "not_validated"


@pytest.mark.asyncio
async def test_unbound_draft_template_can_update_expected_counts(client: AsyncClient) -> None:
    token = await login(client)
    headers = auth_headers(token)

    created = await _create_template(
        client,
        headers,
        name="update-expected-counts",
        expected_ranges_count=1,
        expected_groups_count=1,
    )
    template_id = int(created["id"])

    r = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={
            "expected_ranges_count": 5,
            "expected_groups_count": 8,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["expected_ranges_count"] == 5
    assert body["data"]["expected_groups_count"] == 8
    assert body["data"]["expected_matrix_cells_count"] == 40
    assert body["data"]["validation_status"] == "not_validated"


@pytest.mark.asyncio
async def test_bound_template_cannot_rename(client: AsyncClient) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_bindable_template(
        client,
        headers,
        name="bound-cannot-rename",
    )
    await _bind_template_to_warehouse(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )

    r = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"name": "bound-template-renamed"},
    )
    assert r.status_code == 400, r.text
    assert "Validated template cannot be modified" in r.text


@pytest.mark.asyncio
async def test_bound_template_cannot_update_expected_counts(client: AsyncClient) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_bindable_template(
        client,
        headers,
        name="bound-cannot-update-expected-counts",
    )
    await _bind_template_to_warehouse(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )

    r = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"expected_ranges_count": 2},
    )
    assert r.status_code == 400, r.text
    assert "Validated template cannot be modified" in r.text


@pytest.mark.asyncio
async def test_bound_template_cannot_archive(client: AsyncClient) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_bindable_template(
        client,
        headers,
        name="bound-cannot-archive",
    )
    await _bind_template_to_warehouse(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )

    r = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"status": "archived"},
    )
    assert r.status_code == 409, r.text
    assert "pricing_template is bound; unbind it before archiving" in r.text
