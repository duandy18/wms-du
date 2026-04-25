# tests/api/test_stock_ledger_lot_code_alias_api.py
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_batch_slot


async def _login_admin_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/users/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _matched_seed_rows(
    body: dict,
    *,
    item_id: int,
    warehouse_id: int,
    lot_code: str,
) -> list[dict]:
    rows = body.get("items")
    assert isinstance(rows, list), body

    matched: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if int(row.get("item_id") or 0) != int(item_id):
            continue
        if int(row.get("warehouse_id") or 0) != int(warehouse_id):
            continue
        if row.get("lot_code") != lot_code:
            continue
        if "batch_code" in row:
            continue
        matched.append(row)

    return matched


@pytest.mark.asyncio
async def test_stock_ledger_query_accepts_lot_code_only(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    /stock/ledger/query API 合同：

    - lot_code 是唯一批次展示码查询字段；
    - batch_code 查询 alias 已退役；
    - 输出只保留 lot_code，不再输出 batch_code；
    - 结构事实仍由 lot_id 承载，不能依赖 stock_ledger.batch_code。
    """
    headers = await _login_admin_headers(client)

    warehouse_id = 1
    item_id = 930001
    lot_code = f"UT-LEDGER-LOT-{uuid4().hex[:8].upper()}"

    await ensure_wh_loc_item(
        session,
        wh=warehouse_id,
        loc=warehouse_id,
        item=item_id,
    )
    await seed_batch_slot(
        session,
        item=item_id,
        loc=warehouse_id,
        code=lot_code,
        qty=11,
        days=180,
    )
    await session.commit()

    response = await client.post(
        "/stock/ledger/query",
        headers=headers,
        json={
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "lot_code": lot_code,
            "limit": 50,
            "offset": 0,
        },
    )
    assert response.status_code == 200, response.text

    body = response.json()
    rows = _matched_seed_rows(
        body,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=lot_code,
    )

    assert rows, body
    assert all(row.get("lot_id") is not None for row in rows)
    assert all(row.get("lot_code") == lot_code for row in rows)
    assert all("batch_code" not in row for row in rows)


@pytest.mark.asyncio
async def test_stock_ledger_query_rejects_retired_batch_code_alias(
    client: AsyncClient,
) -> None:
    """
    batch_code 已从 LedgerQuery 入参退役，传入应被 Pydantic extra=forbid 拒绝。
    """
    headers = await _login_admin_headers(client)

    response = await client.post(
        "/stock/ledger/query",
        headers=headers,
        json={
            "item_id": 930001,
            "warehouse_id": 1,
            "batch_code": "UT-LEDGER-RETIRED-ALIAS",
            "limit": 50,
            "offset": 0,
        },
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert body.get("error_code") == "request_validation_error"
    assert "Extra inputs are not permitted" in response.text
