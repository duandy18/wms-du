# tests/api/test_purchase_orders_receipts_api.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from uuid import uuid4

import pytest
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _login_admin_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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


async def _insert_item_internal_none(session: AsyncSession, *, sku_prefix: str) -> int:
    """
    为 API happy-path 插入稳定测试用 item：
    - supplier_id = 1
    - enabled = true
    - lot_source_policy = INTERNAL_ONLY（标签层不要求 batch_code）
    - expiry_policy = NONE（时间层不要求日期）
    """
    sku = f"{sku_prefix}-{uuid4().hex[:10]}"
    name = f"UT-{sku}"
    row = await session.execute(
        text(
            """
            INSERT INTO items(
              name, sku, uom, enabled, supplier_id,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled,
              has_shelf_life,
              shelf_life_value, shelf_life_unit
            )
            VALUES(
              :name, :sku, 'PCS', TRUE, 1,
              'INTERNAL_ONLY'::lot_source_policy, 'NONE'::expiry_policy, TRUE, FALSE,
              FALSE,
              NULL, NULL
            )
            RETURNING id
            """
        ),
        {"name": name, "sku": sku},
    )
    return int(row.scalar_one())


@pytest.mark.asyncio
async def test_purchase_order_receipts_api_returns_fact_events(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """
    Phase5+：/purchase-orders/{po_id}/receipts 返回的是“已确认事实事件”（台账/ledger 口径）。

    happy-path 约束（去耦合后更稳定）：
    - 标签层：lot_source_policy=INTERNAL_ONLY -> 不要求 batch_code
    - 时间层：expiry_policy=NONE -> 不要求日期
    """
    headers = await _login_admin_headers(client)

    # ✅ 不依赖 baseline，直接插入两条 INTERNAL_ONLY + NONE 的 item
    item_a = await _insert_item_internal_none(session, sku_prefix="UT-API-NONE-A")
    item_b = await _insert_item_internal_none(session, sku_prefix="UT-API-NONE-B")
    await session.commit()

    po = await _create_po_two_lines(client, headers, (item_a, item_b))
    po_id = int(po["id"])
    assert po_id > 0, po

    # 先开始收货（draft）
    r0 = await client.post(f"/purchase-orders/{po_id}/receipts/draft", headers=headers)
    assert r0.status_code == 200, r0.text

    # 三次收货（NONE + INTERNAL_ONLY：不需要 batch/date）
    r1 = await client.post(f"/purchase-orders/{po_id}/receive-line", json={"line_no": 1, "qty": 1}, headers=headers)
    assert r1.status_code == 200, r1.text

    r2 = await client.post(f"/purchase-orders/{po_id}/receive-line", json={"line_no": 1, "qty": 1}, headers=headers)
    assert r2.status_code == 200, r2.text

    r3 = await client.post(f"/purchase-orders/{po_id}/receive-line", json={"line_no": 2, "qty": 3}, headers=headers)
    assert r3.status_code == 200, r3.text

    wb = r3.json()
    receipt_id = int((wb.get("caps") or {}).get("receipt_id") or 0)
    assert receipt_id > 0, wb

    # confirm 才写 ledger
    rc = await client.post(f"/inbound-receipts/{receipt_id}/confirm", headers=headers)
    assert rc.status_code == 200, rc.text

    r = await client.get(f"/purchase-orders/{po_id}/receipts", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)

    assert len(data) >= 2, data
    _assert_refline_contiguous_per_ref(data)

    total_qty = sum(int(x.get("qty") or 0) for x in data)
    assert total_qty == 5, {"total_qty": total_qty, "events": data}

    item_ids = sorted({int(x.get("item_id") or 0) for x in data})
    assert item_ids == sorted([item_a, item_b]), {"item_ids": item_ids, "events": data}
