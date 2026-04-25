from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.utils.ensure_minimal import ensure_supplier_lot_with_stock


async def _login_admin_headers(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_outbound_lot_candidates_returns_seeded_positive_supplier_lot(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    warehouse_id = 1
    item_id = 910001
    lot_code = "UT-OUTBOUND-LOT-CAND-1"
    qty = 7

    await ensure_supplier_lot_with_stock(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=lot_code,
        qty=qty,
    )
    await session.commit()

    headers = await _login_admin_headers(client)

    r = await client.get(
        "/wms/outbound/lot-candidates",
        params={"warehouse_id": warehouse_id, "item_id": item_id},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    data = r.json()
    assert data["warehouse_id"] == warehouse_id
    assert data["item_id"] == item_id
    assert isinstance(data["candidates"], list)
    assert data["candidates"], "seeded positive supplier lot should be returned"

    matched = next(
        (row for row in data["candidates"] if row["lot_code"] == lot_code),
        None,
    )
    assert matched is not None, data

    assert isinstance(matched["lot_id"], int)
    assert matched["lot_id"] >= 1
    assert matched["available_qty"] == qty
    assert matched["production_date"] is not None
    assert matched["expiry_date"] is not None


@pytest.mark.asyncio
async def test_outbound_lot_candidates_rejects_invalid_params(
    client: AsyncClient,
) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get(
        "/wms/outbound/lot-candidates",
        params={"warehouse_id": 0, "item_id": 0},
        headers=headers,
    )
    assert r.status_code == 422, r.text
