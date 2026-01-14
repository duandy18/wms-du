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


async def _receive_line(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    po_id: int,
    *,
    line_no: int,
    qty: int,
    production_date: str | None = None,
    expiry_date: str | None = None,
) -> httpx.Response:
    payload: Dict[str, Any] = {"line_no": line_no, "qty": qty}
    if production_date is not None:
        payload["production_date"] = production_date
    if expiry_date is not None:
        payload["expiry_date"] = expiry_date

    return await client.post(
        f"/purchase-orders/{po_id}/receive-line",
        json=payload,
        headers=headers,
    )


def _find_line(po: Dict[str, Any], line_no: int) -> Dict[str, Any]:
    for ln in po.get("lines") or []:
        if int(ln.get("line_no")) == int(line_no):
            return ln
    raise AssertionError(f"line_no {line_no} not found in po.lines")


async def _fetch_po_ledger_rows(session: AsyncSession, po_id: int) -> List[Dict[str, Any]]:
    ref = f"PO-{po_id}"
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
        {"ref": ref, "reason": reason},
    )
    rows = res.mappings().all()
    return [dict(r) for r in rows]


async def _fetch_stock_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
) -> int:
    res = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks
             WHERE warehouse_id = :wid
               AND item_id = :item_id
               AND batch_code = :batch_code
            """
        ),
        {"wid": warehouse_id, "item_id": item_id, "batch_code": batch_code},
    )
    row = res.first()
    if row is None:
        # stocks 在你的体系里应该被 upsert/ensure；若没有就是事实层断裂
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
    """
    合同：同一 (wid,item_id,batch_code) 的 stocks.qty 必须等于最新一条 ledger.after_qty
    """
    last_by_key: Dict[Tuple[int, int, str], Dict[str, Any]] = {}
    for r in rows:
        key = (int(r["warehouse_id"]), int(r["item_id"]), str(r["batch_code"]))
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
    合同（采购入库的最小可解释闭环）：
    1) receive-line 支持多次收货（累加）并推进 PO 状态；
    2) 有效期商品必须补录 production_date；若无法推算 expiry_date，则必须补录 expiry_date；
    3) 每次成功收货必须写入 stock_ledger（RECEIPT / PO-{id} / ref_line 连续）；
    4) stocks.qty 必须与最新 ledger.after_qty 一致（按 wid+item+batch_code 对齐）。
    """
    headers = await _login_admin_headers(client)

    items = await _get_items_supplier_1(client, headers)

    with_sl = [it for it in items if bool(it.get("has_shelf_life")) is True]
    without_sl = [it for it in items if bool(it.get("has_shelf_life")) is not True]

    assert len(with_sl) >= 1
    assert len(without_sl) >= 1

    item_has_sl = int(with_sl[0]["id"])
    item_no_sl = int(without_sl[0]["id"])
    item_ids = (item_has_sl, item_no_sl)

    po = await _create_po_two_lines(client, headers, item_ids)
    po_id = int(po["id"])

    # 初始：qty_received=0
    assert int(_find_line(po, 1).get("qty_received", 0)) == 0
    assert int(_find_line(po, 2).get("qty_received", 0)) == 0

    # 初始：ledger 无记录
    rows0 = await _fetch_po_ledger_rows(session, po_id)
    assert rows0 == []

    # 负例：缺 production_date → 400，且不写 ledger
    r_bad = await _receive_line(client, headers, po_id, line_no=1, qty=1)
    assert r_bad.status_code == 400, r_bad.text
    assert "必须提供生产日期" in r_bad.json().get("detail", "")

    rows_bad = await _fetch_po_ledger_rows(session, po_id)
    assert rows_bad == []

    # 正例1：有效期商品提供 production_date + expiry_date → 200
    r_ok1 = await _receive_line(
        client,
        headers,
        po_id,
        line_no=1,
        qty=1,
        production_date="2026-01-01",
        expiry_date="2026-06-01",
    )
    assert r_ok1.status_code == 200, r_ok1.text
    po1 = r_ok1.json()
    assert int(_find_line(po1, 1).get("qty_received", 0)) == 1

    rows1 = await _fetch_po_ledger_rows(session, po_id)
    assert len(rows1) == 1, rows1
    _assert_refline_is_contiguous(rows1)
    await _assert_stock_matches_last_ledger(session, rows1)

    # 正例2：再收一次同一行（累加）
    r_ok2 = await _receive_line(
        client,
        headers,
        po_id,
        line_no=1,
        qty=1,
        production_date="2026-01-01",
        expiry_date="2026-06-01",
    )
    assert r_ok2.status_code == 200, r_ok2.text
    po2 = r_ok2.json()
    assert int(_find_line(po2, 1).get("qty_received", 0)) == 2

    rows2 = await _fetch_po_ledger_rows(session, po_id)
    assert len(rows2) == 2, rows2
    _assert_refline_is_contiguous(rows2)
    await _assert_stock_matches_last_ledger(session, rows2)

    # 正例3：收第二行（非有效期商品一次收完 3）
    r_ok3 = await _receive_line(client, headers, po_id, line_no=2, qty=3)
    assert r_ok3.status_code == 200, r_ok3.text
    po3 = r_ok3.json()
    assert int(_find_line(po3, 2).get("qty_received", 0)) == 3

    rows3 = await _fetch_po_ledger_rows(session, po_id)
    assert len(rows3) == 3, rows3
    _assert_refline_is_contiguous(rows3)
    await _assert_stock_matches_last_ledger(session, rows3)

    # 最终状态
    status = str(po3.get("status", "")).upper()
    assert status in ("RECEIVED", "CLOSED"), f"unexpected status={status}"
