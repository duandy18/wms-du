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


async def _create_scheme(client: AsyncClient, token: str) -> int:
    h = auth_headers(token)

    r = await client.post(
        "/shipping-providers/1/pricing-schemes",
        headers=h,
        json={
            "warehouse_id": 1,
            "name": "test-scheme",
        },
    )

    assert r.status_code == 201

    body = r.json()

    return int(body["data"]["id"])


async def _build_scheme_resources(client: AsyncClient, h, scheme_id: int) -> None:
    ranges = [
        {
            "min_kg": 0,
            "max_kg": None,
            "sort_order": 0,
            "default_pricing_mode": "flat",
        }
    ]

    r = await client.put(
        f"/pricing-schemes/{scheme_id}/ranges",
        headers=h,
        json={"ranges": ranges},
    )

    assert r.status_code == 200, r.text

    range_id = int(r.json()["ranges"][0]["id"])

    r = await client.post(
        f"/pricing-schemes/{scheme_id}/groups",
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
        f"/pricing-schemes/{scheme_id}/matrix-cells",
        headers=h,
        json={"cells": cells},
    )

    assert r.status_code == 200, r.text

    r = await client.get(
        f"/pricing-schemes/{scheme_id}/matrix-cells",
        headers=h,
    )

    assert r.status_code == 200, r.text
    assert len(r.json()["cells"]) == 1


@pytest.mark.asyncio
async def test_ranges_groups_cells_replace_and_publish(client: AsyncClient):
    token = await login(client)

    h = auth_headers(token)

    scheme_id = await _create_scheme(client, token)

    await _build_scheme_resources(client, h, scheme_id)

    r = await client.post(
        f"/pricing-schemes/{scheme_id}/publish",
        headers=h,
    )

    assert r.status_code == 200, r.text
