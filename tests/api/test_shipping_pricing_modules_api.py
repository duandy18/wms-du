from __future__ import annotations

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

    assert r.status_code == 200

    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_template(client: AsyncClient, token: str) -> int:
    h = auth_headers(token)

    r = await client.post(
        "/tms/pricing/templates",
        headers=h,
        json={
            "shipping_provider_id": 1,
            "name": "test-template",
        },
    )

    assert r.status_code == 201, r.text

    body = r.json()

    return int(body["data"]["id"])


async def _build_template_resources(client: AsyncClient, h, template_id: int) -> None:
    ranges = [
        {
            "min_kg": 0,
            "max_kg": None,
            "sort_order": 0,
            "default_pricing_mode": "flat",
        }
    ]

    r = await client.put(
        f"/tms/pricing/templates/{template_id}/ranges",
        headers=h,
        json={"ranges": ranges},
    )

    assert r.status_code == 200, r.text

    range_id = int(r.json()["ranges"][0]["id"])

    r = await client.post(
        f"/tms/pricing/templates/{template_id}/groups",
        headers=h,
        json={
            "sort_order": 0,
            "active": True,
            "provinces": [{"province_name": "北京市"}],
        },
    )

    assert r.status_code == 200, r.text

    group_id = int(r.json()["group"]["id"])

    cells = [
        {
            "group_id": group_id,
            "module_range_id": range_id,
            "pricing_mode": "flat",
            "flat_amount": 10,
            "active": True,
        }
    ]

    r = await client.put(
        f"/tms/pricing/templates/{template_id}/matrix-cells",
        headers=h,
        json={"cells": cells},
    )

    assert r.status_code == 200, r.text

    r = await client.get(
        f"/tms/pricing/templates/{template_id}/matrix-cells",
        headers=h,
    )

    assert r.status_code == 200, r.text
    assert len(r.json()["cells"]) == 1


@pytest.mark.asyncio
async def test_ranges_groups_cells_replace_and_detail_readable(client: AsyncClient):
    token = await login(client)

    h = auth_headers(token)

    template_id = await _create_template(client, token)

    await _build_template_resources(client, h, template_id)

    detail = await client.get(
        f"/tms/pricing/templates/{template_id}",
        headers=h,
    )

    assert detail.status_code == 200, detail.text
    body = detail.json()

    assert body["ok"] is True
    assert body["data"]["id"] == template_id
    assert body["data"]["status"] == "draft"
    assert isinstance(body["data"]["destination_groups"], list)
    assert len(body["data"]["destination_groups"]) == 1
    assert isinstance(body["data"]["surcharge_configs"], list)

    matrix = await client.get(
        f"/tms/pricing/templates/{template_id}/matrix-cells",
        headers=h,
    )
    assert matrix.status_code == 200, matrix.text
    matrix_body = matrix.json()
    assert matrix_body["ok"] is True
    assert len(matrix_body["cells"]) == 1
