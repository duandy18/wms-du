# tests/api/test_purchase_orders_receive_line_contract.py
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


async def _get_items_supplier_1(client: httpx.AsyncClient, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    r = await client.get("/items?supplier_id=1&enabled=true", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    return data


async def _pick_any_uom_id(session: AsyncSession, *, item_id: int) -> int:
    r1 = await session.execute(
        text(
            """
            SELECT id
              FROM item_uoms
             WHERE item_id = :i AND is_base = true
             ORDER BY id
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    got = r1.scalar_one_or_none()
    if got is not None:
        return int(got)

    r2 = await session.execute(
        text(
            """
            SELECT id
              FROM item_uoms
             WHERE item_id = :i
             ORDER BY id
             LIMIT 1
            """
        ),
        {"i": int(item_id)},
    )
    got2 = r2.scalar_one_or_none()
    assert got2 is not None, {"msg": "item has no item_uoms", "item_id": int(item_id)}
    return int(got2)


async def _insert_item_internal_none(session: AsyncSession, *, sku_prefix: str) -> int:
    """
    为 API happy-path 插入稳定测试用 item：
    - supplier_id = 1
    - enabled = true
    - lot_source_policy = INTERNAL_ONLY（标签层不要求 batch_code）
    - expiry_policy = NONE（时间层不要求日期）
    - Phase M-5：items.uom / has_shelf_life 已删除；单位真相源唯一为 item_uoms
    """
    sku = f"{sku_prefix}-{uuid4().hex[:10]}"
    name = f"UT-{sku}"

    row = await session.execute(
        text(
            """
            INSERT INTO items(
              name, sku, enabled, supplier_id,
              lot_source_policy, expiry_policy, derivation_allowed, uom_governance_enabled,
              shelf_life_value, shelf_life_unit
            )
            VALUES(
              :name, :sku, TRUE, 1,
              'INTERNAL_ONLY'::lot_source_policy, 'NONE'::expiry_policy, TRUE, TRUE,
              NULL, NULL
            )
            RETURNING id
            """
        ),
        {"name": name, "sku": sku},
    )
    item_id = int(row.scalar_one())

    # 单位真相：为该 item 写入 base+defaults（PCS, ratio=1）
    await session.execute(
        text(
            """
            INSERT INTO item_uoms(
              item_id, uom, ratio_to_base, display_name,
              is_base, is_purchase_default, is_inbound_default, is_outbound_default
            )
            VALUES(
              :i, 'PCS', 1, 'PCS',
              TRUE, TRUE, TRUE, TRUE
            )
            ON CONFLICT ON CONSTRAINT uq_item_uoms_item_uom
            DO UPDATE SET
              ratio_to_base = EXCLUDED.ratio_to_base,
              display_name = EXCLUDED.display_name,
              is_base = EXCLUDED.is_base,
              is_purchase_default = EXCLUDED.is_purchase_default,
              is_inbound_default = EXCLUDED.is_inbound_default,
              is_outbound_default = EXCLUDED.is_outbound_default
            """
        ),
        {"i": int(item_id)},
    )

    return item_id


async def _create_po_two_lines(
    session: AsyncSession,
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    item_ids: Tuple[int, int],
) -> Dict[str, Any]:
    item1, item2 = item_ids
    uom1 = await _pick_any_uom_id(session, item_id=int(item1))
    uom2 = await _pick_any_uom_id(session, item_id=int(item2))

    payload = {
        "supplier": "S1",
        "warehouse_id": 1,
        "supplier_id": 1,
        "supplier_name": "S1",
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [
            {"line_no": 1, "item_id": int(item1), "uom_id": int(uom1), "qty_input": 2},
            {"line_no": 2, "item_id": int(item2), "uom_id": int(uom2), "qty_input": 3},
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
    expect_status: int = 200,
    batch_code: str | None = None,
    production_date: str | None = None,
    expiry_date: str | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"line_no": line_no, "qty": qty}
    if batch_code is not None:
        payload["batch_code"] = batch_code
    if production_date is not None:
        payload["production_date"] = production_date
    if expiry_date is not None:
        payload["expiry_date"] = expiry_date

    r = await client.post(
        f"/purchase-orders/{po_id}/receive-line",
        json=payload,
        headers=headers,
    )
    assert r.status_code == int(expect_status), r.text
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
    """
    Phase M-5：ledger 粒度=lot_id；batch_code 仅为展示，不作为测试依赖字段。
    """
    reason = "RECEIPT"
    res = await session.execute(
        text(
            """
            SELECT
              l.reason,
              l.ref,
              l.ref_line,
              l.warehouse_id,
              l.item_id,
              l.lot_id,
              COALESCE(lo.lot_code, '') AS lot_code,
              l.delta,
              l.after_qty
              FROM stock_ledger l
              LEFT JOIN lots lo ON lo.id = l.lot_id
             WHERE l.ref = :ref
               AND l.reason = :reason
             ORDER BY l.ref_line ASC
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
    lot_id: int | None,
) -> int:
    if lot_id is None:
        res = await session.execute(
            text(
                """
                SELECT COALESCE(qty, 0) AS qty
                  FROM stocks_lot
                 WHERE warehouse_id = :wid
                   AND item_id = :item_id
                   AND lot_id IS NULL
                 LIMIT 1
                """
            ),
            {"wid": int(warehouse_id), "item_id": int(item_id)},
        )
        return int(res.scalar_one_or_none() or 0)

    res = await session.execute(
        text(
            """
            SELECT COALESCE(qty, 0) AS qty
              FROM stocks_lot
             WHERE warehouse_id = :wid
               AND item_id = :item_id
               AND lot_id = :lot_id
             LIMIT 1
            """
        ),
        {"wid": int(warehouse_id), "item_id": int(item_id), "lot_id": int(lot_id)},
    )
    return int(res.scalar_one_or_none() or 0)


def _assert_refline_is_contiguous(rows: List[Dict[str, Any]]) -> None:
    ref_lines = [int(r["ref_line"]) for r in rows]
    assert ref_lines == list(range(1, len(rows) + 1)), f"ref_line not contiguous: {ref_lines}"


async def _assert_stock_matches_last_ledger(
    session: AsyncSession,
    rows: List[Dict[str, Any]],
) -> None:
    """
    Phase M-5：按 (warehouse_id, item_id, lot_id|NULL) 粒度，对齐 stocks_lot.qty 与最后一条 ledger.after_qty。
    """
    last_by_key: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
    for r in rows:
        lot_id = r.get("lot_id")
        lot_key = int(lot_id) if lot_id is not None else 0
        key = (int(r["warehouse_id"]), int(r["item_id"]), lot_key)
        last_by_key[key] = r

    for (wid, item_id, lot_key), last in last_by_key.items():
        lot_id = None if lot_key == 0 else int(lot_key)
        qty = await _fetch_stock_qty(session, warehouse_id=wid, item_id=item_id, lot_id=lot_id)
        assert qty == int(last["after_qty"]), {
            "msg": "stocks_lot qty must equal last ledger.after_qty (by lot_id grain)",
            "wid": wid,
            "item_id": item_id,
            "lot_id": lot_id,
            "stocks_lot.qty": qty,
            "ledger.after_qty": int(last["after_qty"]),
            "ledger.ref_line": int(last["ref_line"]),
            "ledger.lot_code": last.get("lot_code"),
        }


def _is_required_expiry_policy(v: Any) -> bool:
    return str(v or "").strip().upper() == "REQUIRED"


@pytest.mark.asyncio
async def test_receive_line_multi_commits_update_qty_and_status(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    # ✅ happy-path items 不依赖 baseline：直接插两条 NONE + INTERNAL_ONLY
    item_none_a = await _insert_item_internal_none(session, sku_prefix="UT-API-NONE-A")
    item_none_b = await _insert_item_internal_none(session, sku_prefix="UT-API-NONE-B")
    await session.commit()

    # 负例 REQUIRED item：仍用 baseline 找一个 REQUIRED（系统应当至少有一个）
    items = await _get_items_supplier_1(client, headers)
    with_required = [it for it in items if _is_required_expiry_policy(it.get("expiry_policy"))]
    assert len(with_required) >= 1, {"msg": "need at least 1 REQUIRED item in baseline", "items": items}
    item_required_obj = with_required[0]
    item_required = int(item_required_obj["id"])

    # 负例：REQUIRED 商品缺必要字段（由 policy 决定缺哪些）
    po_bad = await _create_po_two_lines(session, client, headers, (item_required, item_none_a))
    po_bad_id = int(po_bad["id"])
    await _start_draft(client, headers, po_bad_id)

    # SUPPLIER_ONLY 的 REQUIRED item：不传 batch_code 应被拒绝（http 400）
    bad = await _receive_line(client, headers, po_bad_id, line_no=1, qty=1, expect_status=400)
    assert int(bad.get("http_status") or 0) == 400, bad
    assert "批次码必填" in str(bad.get("message") or ""), bad

    # ✅ 正例：happy-path 全部使用 NONE + INTERNAL_ONLY
    po = await _create_po_two_lines(session, client, headers, (item_none_a, item_none_b))
    po_id = int(po["id"])
    await _start_draft(client, headers, po_id)

    wb1 = await _receive_line(client, headers, po_id, line_no=1, qty=1)
    assert int(_find_row(wb1, 1).get("draft_received_qty") or 0) == 1

    wb2 = await _receive_line(client, headers, po_id, line_no=1, qty=1)
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

    assert len(rows) >= 2, rows
    _assert_refline_is_contiguous(rows)

    total_delta = sum(int(r.get("delta") or 0) for r in rows)
    assert total_delta == 5, {"total_delta": total_delta, "rows": rows}

    item_ids = sorted({int(r.get("item_id") or 0) for r in rows})
    assert item_ids == sorted([item_none_a, item_none_b]), {"item_ids": item_ids, "rows": rows}

    await _assert_stock_matches_last_ledger(session, rows)
