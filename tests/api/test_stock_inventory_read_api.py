# tests/api/test_stock_inventory_read_api.py
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers.inventory import ensure_wh_loc_item, seed_supplier_lot_slot


async def _login_admin_headers(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_stock_options_returns_warehouses_and_items(client: AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/stock/options", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    assert isinstance(data, dict)

    warehouses = data.get("warehouses")
    items = data.get("items")

    assert isinstance(warehouses, list)
    assert isinstance(items, list)

    if warehouses:
        first_wh = warehouses[0]
        assert isinstance(first_wh, dict)
        assert {"id", "name", "active"} <= set(first_wh.keys())
        assert isinstance(first_wh["id"], int)
        assert isinstance(first_wh["name"], str)
        assert isinstance(first_wh["active"], bool)

    if items:
        first_item = items[0]
        assert isinstance(first_item, dict)
        assert {"id", "sku", "name"} <= set(first_item.keys())
        assert isinstance(first_item["id"], int)
        assert isinstance(first_item["sku"], str)
        assert isinstance(first_item["name"], str)


@pytest.mark.asyncio
async def test_stock_inventory_returns_inventory_rows_with_lot_code_only(client: AsyncClient) -> None:
    headers = await _login_admin_headers(client)

    r = await client.get("/stock/inventory?limit=5&offset=0", headers=headers)
    assert r.status_code == 200, r.text

    data = r.json()
    assert isinstance(data, dict)
    assert {"total", "offset", "limit", "rows"} <= set(data.keys())

    assert isinstance(data["total"], int)
    assert isinstance(data["offset"], int)
    assert isinstance(data["limit"], int)
    assert isinstance(data["rows"], list)

    if data["rows"]:
        row = data["rows"][0]
        assert isinstance(row, dict)

        # 主合同：库存页主读面只暴露 lot_code，不再暴露 batch_code
        assert {"item_id", "item_name", "warehouse_id", "lot_code", "qty", "near_expiry"} <= set(row.keys())
        assert "batch_code" not in row

        assert isinstance(row["item_id"], int)
        assert isinstance(row["item_name"], str)
        assert isinstance(row["warehouse_id"], int)
        assert row["lot_code"] is None or isinstance(row["lot_code"], str)
        assert isinstance(row["qty"], int)
        assert isinstance(row["near_expiry"], bool)

        if "days_to_expiry" in row and row["days_to_expiry"] is not None:
            assert isinstance(row["days_to_expiry"], int)


@pytest.mark.asyncio
async def test_stock_inventory_detail_returns_totals_and_slices(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    # 不依赖 baseline 是否刚好存在库存；测试内显式种一条 lot-world 库存
    item_id = 910001
    warehouse_id = 1
    lot_code = "UT-STOCK-DETAIL-001"

    # 先确保基础行存在；否则直接 UPDATE items 可能打空
    await ensure_wh_loc_item(session, wh=warehouse_id, loc=warehouse_id, item=item_id)

    # 当前主链：新建 SUPPLIER lot 前，测试商品必须显式走 REQUIRED
    await session.execute(
        text("UPDATE items SET expiry_policy='REQUIRED'::expiry_policy WHERE id=:i"),
        {"i": int(item_id)},
    )

    await seed_supplier_lot_slot(
        session,
        item=item_id,
        loc=warehouse_id,
        lot_code=lot_code,
        qty=7,
        days=180,
    )
    await session.commit()

    list_resp = await client.get(
        f"/stock/inventory?item_id={item_id}&warehouse_id={warehouse_id}&limit=10&offset=0",
        headers=headers,
    )
    assert list_resp.status_code == 200, list_resp.text

    list_data = list_resp.json()
    rows = list_data.get("rows") or []
    assert isinstance(rows, list)
    assert rows, list_data

    seeded = rows[0]
    assert int(seeded["item_id"]) == item_id

    detail_resp = await client.get(f"/stock/inventory/{item_id}/detail?pools=MAIN", headers=headers)
    assert detail_resp.status_code == 200, detail_resp.text

    data = detail_resp.json()
    assert isinstance(data, dict)
    assert {"item_id", "item_name", "totals", "slices"} <= set(data.keys())

    assert data["item_id"] == item_id
    assert isinstance(data["item_name"], str)

    totals = data["totals"]
    assert isinstance(totals, dict)
    assert {"on_hand_qty", "available_qty"} <= set(totals.keys())
    assert isinstance(totals["on_hand_qty"], int)
    assert isinstance(totals["available_qty"], int)

    slices = data["slices"]
    assert isinstance(slices, list)

    if slices:
        first = slices[0]
        assert isinstance(first, dict)
        assert {
            "warehouse_id",
            "warehouse_name",
            "pool",
            "lot_code",
            "production_date",
            "expiry_date",
            "on_hand_qty",
            "available_qty",
            "near_expiry",
            "is_top",
        } <= set(first.keys())

        assert "batch_code" not in first

        assert isinstance(first["warehouse_id"], int)
        assert isinstance(first["warehouse_name"], str)
        assert isinstance(first["pool"], str)
        assert first["lot_code"] is None or isinstance(first["lot_code"], str)
        assert first["production_date"] is None or isinstance(first["production_date"], str)
        assert first["expiry_date"] is None or isinstance(first["expiry_date"], str)
        assert isinstance(first["on_hand_qty"], int)
        assert isinstance(first["available_qty"], int)
        assert isinstance(first["near_expiry"], bool)
        assert isinstance(first["is_top"], bool)
