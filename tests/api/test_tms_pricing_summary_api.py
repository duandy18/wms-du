from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _login(client: AsyncClient) -> str:
    r = await client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    token = body.get("access_token")
    assert isinstance(token, str) and token, body
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_pricing_list_returns_template_not_active_row_from_seed(client: AsyncClient) -> None:
    token = await _login(client)
    h = _auth_headers(token)

    r = await client.get("/tms/pricing/list", headers=h)
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["ok"] is True
    rows = body["rows"]
    assert isinstance(rows, list) and rows, body

    seed_row = None
    for row in rows:
        if int(row["provider_id"]) == 1 and int(row["warehouse_id"]) == 1:
            seed_row = row
            break

    assert seed_row is not None, rows
    assert seed_row["provider_code"] == "UT-CAR-1"
    assert seed_row["provider_name"] == "UT-CARRIER-1"
    assert seed_row["binding_active"] is True
    assert int(seed_row["active_template_id"]) == 1
    assert seed_row["active_template_name"] == "UT-TEMPLATE-1"
    assert seed_row["active_template_status"] == "draft"
    assert seed_row["is_template_active"] is False
    assert seed_row["pricing_status"] == "template_not_active"


@pytest.mark.asyncio
async def test_pricing_list_returns_no_active_template_for_bound_provider_without_template(
    client: AsyncClient,
) -> None:
    token = await _login(client)
    h = _auth_headers(token)

    create_provider = await client.post(
        "/shipping-providers",
        headers=h,
        json={
            "name": "UT-SUMMARY-NO-TEMPLATE",
            "code": "UTSUMNOTPL",
            "active": True,
            "priority": 50,
            "address": "UT-ADDR-NO-TEMPLATE",
        },
    )
    assert create_provider.status_code in (200, 201), create_provider.text
    provider_body = create_provider.json()
    provider_id = provider_body.get("id")
    if not isinstance(provider_id, int):
        provider_id = (provider_body.get("data", {}) or {}).get("id")
    assert isinstance(provider_id, int) and provider_id > 0, provider_body

    bind = await client.post(
        "/tms/pricing/warehouses/1/bindings",
        headers=h,
        json={
            "shipping_provider_id": provider_id,
            "active": True,
            "priority": 9,
            "pickup_cutoff_time": "18:00",
            "remark": "summary no template",
        },
    )
    assert bind.status_code in (201, 409), bind.text

    if bind.status_code == 409:
        patch = await client.patch(
            f"/tms/pricing/warehouses/1/bindings/{provider_id}",
            headers=h,
            json={
                "active": True,
                "priority": 9,
                "remark": "summary no template",
            },
        )
        assert patch.status_code == 200, patch.text

    r = await client.get("/tms/pricing/list", headers=h)
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["ok"] is True
    rows = body["rows"]
    assert isinstance(rows, list) and rows, body

    target = None
    for row in rows:
        if int(row["provider_id"]) == provider_id and int(row["warehouse_id"]) == 1:
            target = row
            break

    assert target is not None, rows
    assert target["binding_active"] is True
    assert target["active_template_id"] is None
    assert target["active_template_name"] is None
    assert target["active_template_status"] is None
    assert target["is_template_active"] is False
    assert target["pricing_status"] == "no_active_template"
