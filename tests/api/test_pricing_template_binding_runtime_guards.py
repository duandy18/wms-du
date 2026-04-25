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
    assert body["data"]["status"] == "draft"
    assert body["data"]["validation_status"] == "not_validated"
    assert body["data"]["expected_ranges_count"] == int(expected_ranges_count)
    assert body["data"]["expected_groups_count"] == int(expected_groups_count)
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
            "active": True,
            "priority": 0,
            "pickup_cutoff_time": "18:00",
            "remark": "binding-runtime-guard-test",
        },
    )


async def _list_template_candidates(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    warehouse_id: int,
    shipping_provider_id: int,
) -> list[dict]:
    r = await client.get(
        f"/shipping-assist/pricing/warehouses/{warehouse_id}/bindings/{shipping_provider_id}/template-candidates",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    rows = body["data"] or []
    assert isinstance(rows, list), rows
    return rows


async def _create_template_with_stage(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    submit_validation: bool,
    with_ranges: bool,
    with_groups: bool,
    with_matrix: bool,
    expected_ranges_count: int = 1,
    expected_groups_count: int = 1,
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
        expected_ranges_count=expected_ranges_count,
        expected_groups_count=expected_groups_count,
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

    if submit_validation:
        await _submit_validation(
            client,
            headers,
            template_id=template_id,
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
        submit_validation=False,
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
        (False, False, False, "pricing_template not validated"),
        (True, False, False, "Template cannot submit validation in current state"),
        (True, True, False, "Template cannot submit validation in current state"),
    ],
)
async def test_incomplete_structure_cannot_enter_bindable_state(
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
        submit_validation=False,
        with_ranges=with_ranges,
        with_groups=with_groups,
        with_matrix=with_matrix,
    )

    if with_ranges or with_groups or with_matrix:
        submit_resp = await client.post(
            f"/shipping-assist/pricing/templates/{template_id}/submit-validation",
            headers=headers,
            json={"confirm_validated": True},
        )
        assert submit_resp.status_code == 400, submit_resp.text
        assert expected_detail in submit_resp.text

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
async def test_validation_rejects_when_expected_counts_not_met(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_template_with_stage(
        client,
        headers,
        name="bind-guard-expected-counts-not-met",
        submit_validation=False,
        with_ranges=True,
        with_groups=True,
        with_matrix=True,
        expected_ranges_count=2,
        expected_groups_count=1,
    )

    r_submit = await client.post(
        f"/shipping-assist/pricing/templates/{template_id}/submit-validation",
        headers=headers,
        json={"confirm_validated": True},
    )
    assert r_submit.status_code == 400, r_submit.text
    assert "Template cannot submit validation in current state" in r_submit.text

    r_bind = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )
    assert r_bind.status_code == 409, r_bind.text
    assert "pricing_template not validated" in r_bind.text


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
        submit_validation=True,
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


@pytest.mark.asyncio
async def test_template_candidates_only_return_bindable_templates(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_template_with_stage(
        client,
        headers,
        name="bind-candidates-ready-unused",
        submit_validation=True,
        with_ranges=True,
        with_groups=True,
        with_matrix=True,
    )

    rows = await _list_template_candidates(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
    )
    ids = {int(row["id"]) for row in rows}

    assert int(template_id) in ids, rows

    target = next(row for row in rows if int(row["id"]) == int(template_id))
    assert target["validation_status"] == "passed"
    assert target["config_status"] == "ready"
    assert int(target["used_binding_count"]) == 0
    assert target["status"] == "draft"


@pytest.mark.asyncio
async def test_bound_template_disappears_from_template_candidates(
    client: AsyncClient,
) -> None:
    token = await login(client)
    headers = auth_headers(token)

    warehouse_id, shipping_provider_id, template_id = await _create_template_with_stage(
        client,
        headers,
        name="bind-candidates-after-bound",
        submit_validation=True,
        with_ranges=True,
        with_groups=True,
        with_matrix=True,
    )

    before_rows = await _list_template_candidates(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
    )
    before_ids = {int(row["id"]) for row in before_rows}
    assert int(template_id) in before_ids, before_rows

    bind_resp = await _bind_template(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
        template_id=template_id,
    )
    assert bind_resp.status_code == 201, bind_resp.text

    after_rows = await _list_template_candidates(
        client,
        headers,
        warehouse_id=warehouse_id,
        shipping_provider_id=shipping_provider_id,
    )
    after_ids = {int(row["id"]) for row in after_rows}
    assert int(template_id) not in after_ids, after_rows
