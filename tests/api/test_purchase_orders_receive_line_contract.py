# tests/api/test_purchase_orders_receive_line_contract.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
    data = r.json()
    assert "id" in data
    assert isinstance(data.get("lines"), list)
    assert len(data["lines"]) == 2
    return data


async def _start_draft(client: httpx.AsyncClient, headers: Dict[str, str], po_id: int) -> Dict[str, Any]:
    r = await client.post(f"/purchase-orders/{po_id}/receipts/draft", headers=headers)
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
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"line_no": line_no, "qty": qty}
    if production_date is not None:
        payload["production_date"] = production_date
    if expiry_date is not None:
        payload["expiry_date"] = expiry_date

    r = await client.post(
        f"/purchase-orders/{po_id}/receive-line",
        json=payload,
        headers=headers,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert isinstance(out, dict)
    return out


def _find_row(workbench: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    for row in workbench.get("rows") or []:
        if int(row.get("line_no")) == int(line_no):
            return row
    raise AssertionError(f"line_no {line_no} not found in workbench.rows")


async def _confirm_receipt(client: httpx.AsyncClient, headers: Dict[str, str], receipt_id: int) -> Dict[str, Any]:
    r = await client.post(f"/inbound-receipts/{receipt_id}/confirm", headers=headers)
    assert r.status_code == 200, r.text
    out = r.json()
    assert isinstance(out, dict)
    return out


async def _fetch_ledger_rows_by_ref(session: AsyncSession, ref: str) -> List[Dict[str, Any]]:
    reason = "RECEIPT"
    res = await session.execute(
        text(
            """
            SELECT reason, ref, ref_line, warehouse_id, item_id, batch_code, delta, after_qty
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = :reason
             ORDER BY ref_line ASC
            """
        ),
        {"ref": str(ref), "reason": reason},
    )
    rows = res.mappings().all()
    return [dict(r) for r in rows]


async def _fetch_stock_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str | None,
) -> int:
    res = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks
             WHERE warehouse_id = :wid
               AND item_id = :item_id
               AND batch_code IS NOT DISTINCT FROM :batch_code
            """
        ),
        {"wid": warehouse_id, "item_id": item_id, "batch_code": batch_code},
    )
    row = res.first()
    if row is None:
        raise AssertionError(
            f"stocks row not found: wid={warehouse_id}, item_id={item_id}, batch_code={batch_code}"
        )
    return int(row[0])


def _assert_refline_is_contiguous(rows: List[Dict[str, Any]]) -> None:
    ref_lines = [int(r["ref_line"]) for r in rows]
    assert ref_lines == list(range(1, len(rows) + 1)), f"ref_line not contiguous: {ref_lines}"


async def _assert_stock_matches_last_ledger(
    session: AsyncSession,
    rows: List[Dict[str, Any]],
) -> None:
    last_by_key: Dict[Tuple[int, int, str | None], Dict[str, Any]] = {}
    for r in rows:
        key = (int(r["warehouse_id"]), int(r["item_id"]), r.get("batch_code"))
        last_by_key[key] = r

    for (wid, item_id, batch_code), last in last_by_key.items():
        qty = await _fetch_stock_qty(session, warehouse_id=wid, item_id=item_id, batch_code=batch_code)
        assert qty == int(last["after_qty"]), {
            "msg": "stocks.qty must equal last ledger.after_qty",
            "wid": wid,
            "item_id": item_id,
            "batch_code": batch_code,
            "stocks.qty": qty,
            "ledger.after_qty": int(last["after_qty"]),
            "ledger.ref_line": int(last["ref_line"]),
        }


@pytest.mark.asyncio
async def test_receive_line_multi_commits_update_qty_and_status(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    """
    Phase5+ 合同（采购收货闭环）：

    - 显式开始收货（draft）
    - receive-line 返回 workbench，草稿数量累加
    - confirm 是唯一库存写入口：confirm 后才写 stock_ledger/stocks
    """
    headers = await _login_admin_headers(client)

    items = await _get_items_supplier_1(client, headers)
    with_sl = [it for it in items if bool(it.get("has_shelf_life")) is True]
    without_sl = [it for it in items if bool(it.get("has_shelf_life")) is not True]

    assert len(with_sl) >= 1
    assert len(without_sl) >= 1

    item_has_sl = int(with_sl[0]["id"])
    item_no_sl = int(without_sl[0]["id"])

    # 负例：坏草稿会导致 can_confirm=false
    po_bad = await _create_po_two_lines(client, headers, (item_has_sl, item_no_sl))
    po_bad_id = int(po_bad["id"])
    await _start_draft(client, headers, po_bad_id)

    wb_bad = await _receive_line(client, headers, po_bad_id, line_no=1, qty=1)  # 缺 production_date
    exp_bad = wb_bad.get("explain") or {}
    assert bool(exp_bad.get("confirmable")) is False
    caps_bad = wb_bad.get("caps") or {}
    assert bool(caps_bad.get("can_confirm")) is False

    # 正例：新 PO，不带坏行
    po = await _create_po_two_lines(client, headers, (item_has_sl, item_no_sl))
    po_id = int(po["id"])
    await _start_draft(client, headers, po_id)

    wb1 = await _receive_line(
        client, headers, po_id, line_no=1, qty=1, production_date="2026-01-01", expiry_date="2026-01-31"
    )
    assert int(_find_row(wb1, 1).get("draft_received_qty") or 0) == 1

    wb2 = await _receive_line(
        client, headers, po_id, line_no=1, qty=1, production_date="2026-01-01", expiry_date="2026-01-31"
    )
    assert int(_find_row(wb2, 1).get("draft_received_qty") or 0) == 2

    wb3 = await _receive_line(client, headers, po_id, line_no=2, qty=3)
    assert int(_find_row(wb3, 2).get("draft_received_qty") or 0) == 3

    caps = wb3.get("caps") or {}
    receipt_id = int(caps.get("receipt_id") or 0)
    assert receipt_id > 0
    assert bool(caps.get("can_confirm")) is True

    conf = await _confirm_receipt(client, headers, receipt_id)
    receipt_ref = str(conf["receipt"]["ref"])

    rows = await _fetch_ledger_rows_by_ref(session, receipt_ref)
    # ✅ 真实行为：line1 两次会在 confirm 归一化合并为 delta=2 一条；line2 delta=3 一条 → 共 2 条
    assert len(rows) == 2, rows
    _assert_refline_is_contiguous(rows)
    await _assert_stock_matches_last_ledger(session, rows)
