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


def _assert_refline_contiguous_per_ref(events: List[Dict[str, Any]]) -> None:
    """
    Phase5+：ref_line 的合同是「在同一个 ref 维度递增」。
    一个 PO 可能由多张 CONFIRMED receipt（不同 ref）产生事件流，
    因此全局 ref_line 不要求连续。
    """
    by_ref: Dict[str, List[int]] = {}
    for e in events:
        ref = str(e.get("ref") or "")
        by_ref.setdefault(ref, []).append(int(e.get("ref_line") or 0))

    assert by_ref, {"msg": "events must contain at least one ref", "events": events}

    for ref, xs in by_ref.items():
        xs_sorted = sorted(xs)
        assert xs_sorted == list(range(1, len(xs_sorted) + 1)), {
            "msg": "ref_line must be contiguous within same ref",
            "ref": ref,
            "ref_lines": xs_sorted,
        }


@pytest.mark.asyncio
async def test_purchase_order_receipts_api_returns_fact_events(client: httpx.AsyncClient) -> None:
    """
    Phase5+：/purchase-orders/{po_id}/receipts 返回的是“已确认事实事件”（台账/ledger 口径）。

    注意：
    - receive-line 只写 Receipt(DRAFT) 事实，不写 ledger；
    - confirm 才写 ledger；
    - ref_line 的连续性是 per-ref（每张 receipt.ref 自己的序列），不是全局序列。
    """
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

    # Phase5+：先开始收货（draft）
    r0 = await client.post(f"/purchase-orders/{po_id}/receipts/draft", headers=headers)
    assert r0.status_code == 200, r0.text

    # 三次收货（receive-line 返回 workbench）
    r1 = await client.post(
        f"/purchase-orders/{po_id}/receive-line",
        json={"line_no": 1, "qty": 1, "production_date": "2026-01-01", "expiry_date": "2026-01-31"},
        headers=headers,
    )
    assert r1.status_code == 200, r1.text

    r2 = await client.post(
        f"/purchase-orders/{po_id}/receive-line",
        json={"line_no": 1, "qty": 1, "production_date": "2026-01-01", "expiry_date": "2026-01-31"},
        headers=headers,
    )
    assert r2.status_code == 200, r2.text

    r3 = await client.post(
        f"/purchase-orders/{po_id}/receive-line",
        json={"line_no": 2, "qty": 3},
        headers=headers,
    )
    assert r3.status_code == 200, r3.text

    wb = r3.json()
    receipt_id = int((wb.get("caps") or {}).get("receipt_id") or 0)
    assert receipt_id > 0, wb

    # Phase5+：confirm 才产生 receipts 事实事件（ledger）
    rc = await client.post(f"/inbound-receipts/{receipt_id}/confirm", headers=headers)
    assert rc.status_code == 200, rc.text

    r = await client.get(f"/purchase-orders/{po_id}/receipts", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)

    # 基本合同：至少有事件（不同实现下可能 2 条或 3 条，取决于 confirm 归一化/聚合策略）
    assert len(data) >= 2, data

    # ✅ ref_line 连续性应在每个 ref 内成立
    _assert_refline_contiguous_per_ref(data)

    # 关键事实：本次总收货 qty = 1 + 1 + 3 = 5（delta 口径）
    total_qty = sum(int(x.get("qty") or 0) for x in data)
    assert total_qty == 5, {"total_qty": total_qty, "events": data}

    # 事件应只包含这两种 item
    item_ids = sorted({int(x.get("item_id") or 0) for x in data})
    assert item_ids == sorted([item_has_sl, item_no_sl]), {"item_ids": item_ids, "events": data}

    # 有效期行至少应出现一次并带生产/到期
    sl_events = [x for x in data if int(x.get("item_id") or 0) == item_has_sl]
    assert sl_events, {"msg": "expected at least one shelf-life event", "events": data}
    assert sl_events[0].get("production_date") is not None
    assert sl_events[0].get("expiry_date") is not None
