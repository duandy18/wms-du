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

    suffix = int(time.time() * 1000) % 1_000_000
    return await _create_shipping_provider(
        client,
        headers,
        name=f"TEST-BIND-GUARD-PROVIDER-{suffix}",
        code=f"TBGP{suffix}",
    )


async def _create_template(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    shipping_provider_id: int,
    name: str,
) -> int:
    r = await client.post(
        "/tms/pricing/templates",
        headers=headers,
        json={
            "shipping_provider_id": int(shipping_provider_id),
            "name": name,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["status"] == "draft"
    assert body["data"]["validation_status"] == "not_validated"
    return int(body["data"]["id"])


async def _put_ranges(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    template_id: int,
) -> int:
    r = await client.put(
        f"/tms/pricing/templates/{template_id}/ranges",
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
        f"/tms/pricing/templates/{template_id}/groups",
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
        f"/tms/pricing/templates/{template_id}/matrix-cells",
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


async def _set_validation_status(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    template_id: int,
    validation_status: str,
) -> None:
    r = await client.patch(
        f"/tms/pricing/templates/{template_id}",
        headers=headers,
        json={"validation_status": validation_status},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["validation_status"] == validation_status


async def _bind_template(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    warehouse_id: int,
    shipping_provider_id: int,
    template_id: int,
):
    return await client.post(
        f"/tms/pricing/warehouses/{warehouse_id}/bindings",
        headers=headers,
        json={
            "shipping_provider_id": int(shipping_provider_id),
            "active_template_id": int(template_id),
            "active": True,
            "priority": 0,
            "pickup_cutoff_time": "18:00",
            "remark": "binding-runtime-guard-test",
        },
    )


async def _create_template_with_stage(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    validation_status: str,
    with_ranges: bool,
    with_groups: bool,
    with_matrix: bool,
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

    range_id: int | None = None
    group_id: int | None = None

    if with_ranges:
        range_id = await _put_ranges(
            client,
            headers,
            template_id=template_id,
        )

    if with_groups:
        group_id = await _post_group(
            client,
            headers,
            template_id=template_id,
        )

    if with_matrix:
        assert range_id is not None
        assert group_id is not None
        await _put_single_matrix_cell(
            client,
            headers,
            template_id=template_id,
            group_id=group_id,
            range_id=range_id,
        )

    await _set_validation_status(
        client,
        headers,
        template_id=template_id,
        validation_status=validation_status,
    )

    return warehouse_id, shipping_provider_id, template_id


@pytest.mark.asyncio
async def test_unvalidated_template_cannot_bind_even_if_structure_complete(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_template_with_stage(
        client,
        headers,
        name="bind-guard-not-validated",
        validation_status="not_validated",
        with_ranges=True,
        with_groups=True,
        with_matrix=True,
    )

    r = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )
    assert r.status_code == 409, r.text
    assert "pricing_template not validated" in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("with_ranges", "with_groups", "with_matrix", "expected_detail"),
    [
        (False, False, False, "pricing_template invalid: template has no weight ranges"),
        (True, False, False, "pricing_template invalid: template has no destination groups"),
        (True, True, False, "pricing_template invalid: template pricing matrix incomplete"),
    ],
)
async def test_passed_template_with_incomplete_structure_cannot_bind(
    client: AsyncClient,
    with_ranges: bool,
    with_groups: bool,
    with_matrix: bool,
    expected_detail: str,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_template_with_stage(
        client,
        headers,
        name=f"bind-guard-incomplete-{int(with_ranges)}-{int(with_groups)}-{int(with_matrix)}",
        validation_status="passed",
        with_ranges=with_ranges,
        with_groups=with_groups,
        with_matrix=with_matrix,
    )

    r = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )
    assert r.status_code == 409, r.text
    assert expected_detail in r.text


@pytest.mark.asyncio
async def test_passed_template_with_complete_structure_can_bind(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_template_with_stage(
        client,
        headers,
        name="bind-guard-ready-can-bind",
        validation_status="passed",
        with_ranges=True,
        with_groups=True,
        with_matrix=True,
    )

    r = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    assert int(body["data"]["shipping_provider_id"]) == int(shipping_provider_id)
    assert int(body["data"]["active_template_id"]) == int(template_id)
