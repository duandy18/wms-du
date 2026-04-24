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
        if row.get("batch_code") != lot_code:
            continue
        matched.append(row)

    return matched


@pytest.mark.asyncio
async def test_stock_ledger_query_accepts_lot_code_and_batch_code_aliases(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    /stock/ledger/query API 合同：

    - lot_code 是正名查询字段；
    - batch_code 是历史兼容查询字段；
    - 两者查询同一个 lots.lot_code 时，必须命中同一批 ledger 行；
    - 输出继续保留 lot_code + batch_code，且二者等价；
    - 结构事实仍由 lot_id 承载，不能依赖 stock_ledger.batch_code。
    """
    headers = await _login_admin_headers(client)

    warehouse_id = 1
    item_id = 930001
    lot_code = f"UT-LEDGER-ALIAS-{uuid4().hex[:8].upper()}"

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

    common_payload = {
        "item_id": item_id,
        "warehouse_id": warehouse_id,
        "limit": 50,
        "offset": 0,
    }

    by_lot_code = await client.post(
        "/stock/ledger/query",
        headers=headers,
        json={
            **common_payload,
            "lot_code": lot_code,
        },
    )
    assert by_lot_code.status_code == 200, by_lot_code.text

    by_batch_code = await client.post(
        "/stock/ledger/query",
        headers=headers,
        json={
            **common_payload,
            "batch_code": lot_code,
        },
    )
    assert by_batch_code.status_code == 200, by_batch_code.text

    lot_body = by_lot_code.json()
    batch_body = by_batch_code.json()

    lot_rows = _matched_seed_rows(
        lot_body,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=lot_code,
    )
    batch_rows = _matched_seed_rows(
        batch_body,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=lot_code,
    )

    assert lot_rows, lot_body
    assert batch_rows, batch_body

    lot_row_ids = {int(row["id"]) for row in lot_rows}
    batch_row_ids = {int(row["id"]) for row in batch_rows}

    assert lot_row_ids == batch_row_ids
    assert all(row.get("lot_id") is not None for row in lot_rows)
    assert all(row.get("batch_code") == row.get("lot_code") == lot_code for row in lot_rows)


@pytest.mark.asyncio
async def test_stock_ledger_query_rejects_conflicting_lot_code_aliases(
    client: AsyncClient,
) -> None:
    """
    lot_code 和 batch_code 同时传入时，归一后必须一致。
    """
    headers = await _login_admin_headers(client)

    response = await client.post(
        "/stock/ledger/query",
        headers=headers,
        json={
            "item_id": 930001,
            "warehouse_id": 1,
            "lot_code": "UT-LEDGER-ALIAS-A",
            "batch_code": "UT-LEDGER-ALIAS-B",
            "limit": 50,
            "offset": 0,
        },
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert isinstance(body, dict)
    assert body.get("error_code") == "lot_code_alias_conflict"
