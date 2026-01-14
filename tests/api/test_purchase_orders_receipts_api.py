# tests/api/test_purchase_orders_receipts_api.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest
import httpx


async def _login_admin_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _get_items_supplier_1(client: httpx.AsyncClient, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    r = await client.get("/items?supplier_id=1&enabled=true", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    return data


async def _create_po_two_lines(
    client: httpx.AsyncClient, headers: Dict[str, str], item_ids: Tuple[int, int]
) -> Dict[str, Any]:
    item1, item2 = item_ids
    payload = {
        "supplier": "S1",
        "warehouse_id": 1,
        "supplier_id": 1,
        "supplier_name": "S1",
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [
            {"line_no": 1, "item_id": item1, "qty_ordered": 2},
            {"line_no": 2, "item_id": item2, "qty_ordered": 3},
        ],
    }
    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _receive_line(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    po_id: int,
    *,
    line_no: int,
    qty: int,
    production_date: str | None = None,
    expiry_date: str | None = None,
) -> None:
    payload: Dict[str, Any] = {"line_no": line_no, "qty": qty}
    if production_date is not None:
        payload["production_date"] = production_date
    if expiry_date is not None:
        payload["expiry_date"] = expiry_date

    r = await client.post(f"/purchase-orders/{po_id}/receive-line", json=payload, headers=headers)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_purchase_order_receipts_api_returns_fact_events(client: httpx.AsyncClient) -> None:
    headers = await _login_admin_headers(client)
    items = await _get_items_supplier_1(client, headers)

    with_sl = [it for it in items if bool(it.get("has_shelf_life")) is True]
    without_sl = [it for it in items if bool(it.get("has_shelf_life")) is not True]
    assert len(with_sl) >= 1
    assert len(without_sl) >= 1

    item_has_sl = int(with_sl[0]["id"])
    item_no_sl = int(without_sl[0]["id"])

    po = await _create_po_two_lines(client, headers, (item_has_sl, item_no_sl))
    po_id = int(po["id"])

    # 三次收货：1) line1 qty=1（有效期补录） 2) line1 qty=1（有效期补录） 3) line2 qty=3
    await _receive_line(client, headers, po_id, line_no=1, qty=1, production_date="2026-01-01", expiry_date="2026-06-01")
    await _receive_line(client, headers, po_id, line_no=1, qty=1, production_date="2026-01-01", expiry_date="2026-06-01")
    await _receive_line(client, headers, po_id, line_no=2, qty=3)

    r = await client.get(f"/purchase-orders/{po_id}/receipts", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 3

    # ref_line 连续 1..3（与台账合同一致）
    assert [int(x["ref_line"]) for x in data] == [1, 2, 3]

    # qty 与本次收货一致（delta）
    assert [int(x["qty"]) for x in data] == [1, 1, 3]

    # item_id 顺序与收货顺序一致
    assert [int(x["item_id"]) for x in data] == [item_has_sl, item_has_sl, item_no_sl]

    # line_no 能映射（允许为 None，但在单 item 单行的 PO 下应稳定给出）
    assert [int(x["line_no"]) for x in data] == [1, 1, 2]

    # 有效期行必须带生产/到期
    assert data[0]["production_date"] is not None
    assert data[0]["expiry_date"] is not None
