# tests/api/test_purchase_orders_completion_api.py
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
) -> Tuple[Dict[str, Any], Dict[int, int]]:
    item1, item2 = item_ids
    uom1 = await _pick_any_uom_id(session, item_id=int(item1))
    uom2 = await _pick_any_uom_id(session, item_id=int(item2))

    payload = {
        "warehouse_id": 1,
        "supplier_id": 1,
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
    assert isinstance(data, dict), data
    assert int(data.get("id") or 0) > 0, data
    assert str(data.get("po_no") or "").startswith("PO-"), data
    assert isinstance(data.get("lines"), list) and len(data["lines"]) == 2, data
    return data, {1: int(uom1), 2: int(uom2)}


async def _commit_purchase_inbound(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    *,
    po: Dict[str, Any],
    uom_map: Dict[int, int],
) -> Dict[str, Any]:
    po_id = int(po["id"])
    po_no = str(po["po_no"])
    lines = list(po["lines"])

    by_line_no = {int(x["line_no"]): x for x in lines}

    payload = {
        "warehouse_id": 1,
        "source_type": "PURCHASE_ORDER",
        "source_ref": po_no,
        "occurred_at": "2026-01-14T10:30:00Z",
        "remark": f"completion test for po_id={po_id}",
        "lines": [
            {
                "item_id": int(by_line_no[1]["item_id"]),
                "uom_id": int(uom_map[1]),
                "qty_input": 1,
                "po_line_id": int(by_line_no[1]["id"]),
            },
            {
                "item_id": int(by_line_no[1]["item_id"]),
                "uom_id": int(uom_map[1]),
                "qty_input": 1,
                "po_line_id": int(by_line_no[1]["id"]),
            },
            {
                "item_id": int(by_line_no[2]["item_id"]),
                "uom_id": int(uom_map[2]),
                "qty_input": 3,
                "po_line_id": int(by_line_no[2]["id"]),
            },
        ],
    }

    r = await client.post("/wms/inbound/commit", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    out = r.json()
    assert isinstance(out, dict), out
    assert int(out.get("event_id") or 0) > 0, out
    assert str(out.get("event_no") or "").startswith("IE-"), out
    assert str(out.get("trace_id") or "").startswith("IN-COMMIT-"), out
    assert str(out.get("source_type") or "") == "PURCHASE_ORDER", out
    assert str(out.get("source_ref") or "") == po_no, out
    assert isinstance(out.get("rows"), list) and len(out["rows"]) == 3, out
    return out


def _rows_for_po(rows: List[Dict[str, Any]], *, po_id: int) -> List[Dict[str, Any]]:
    return [r for r in rows if int(r.get("po_id") or 0) == int(po_id)]


@pytest.mark.asyncio
async def test_purchase_orders_completion_list_returns_line_level_completion(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    item_a = await _insert_item_internal_none(session, sku_prefix="UT-COMP-LIST-A")
    item_b = await _insert_item_internal_none(session, sku_prefix="UT-COMP-LIST-B")
    await session.commit()

    po, uom_map = await _create_po_two_lines(session, client, headers, (item_a, item_b))
    po_id = int(po["id"])
    po_no = str(po["po_no"])

    await _commit_purchase_inbound(client, headers, po=po, uom_map=uom_map)

    r = await client.get(f"/purchase-orders/completion?q={po_no}", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list), data

    rows = _rows_for_po(data, po_id=po_id)
    assert len(rows) == 2, rows

    rows_by_line_no = {int(x["line_no"]): x for x in rows}

    line1 = rows_by_line_no[1]
    assert int(line1["po_id"]) == po_id
    assert str(line1["po_no"]) == po_no
    assert int(line1["item_id"]) == int(item_a)
    assert int(line1["qty_ordered_base"]) == 2
    assert int(line1["qty_received_base"]) == 2
    assert int(line1["qty_remaining_base"]) == 0
    assert str(line1["line_completion_status"]) == "RECEIVED"

    line2 = rows_by_line_no[2]
    assert int(line2["po_id"]) == po_id
    assert str(line2["po_no"]) == po_no
    assert int(line2["item_id"]) == int(item_b)
    assert int(line2["qty_ordered_base"]) == 3
    assert int(line2["qty_received_base"]) == 3
    assert int(line2["qty_remaining_base"]) == 0
    assert str(line2["line_completion_status"]) == "RECEIVED"


@pytest.mark.asyncio
async def test_purchase_orders_completion_detail_returns_summary_lines_and_events(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    item_a = await _insert_item_internal_none(session, sku_prefix="UT-COMP-DETAIL-A")
    item_b = await _insert_item_internal_none(session, sku_prefix="UT-COMP-DETAIL-B")
    await session.commit()

    po, uom_map = await _create_po_two_lines(session, client, headers, (item_a, item_b))
    po_id = int(po["id"])
    po_no = str(po["po_no"])

    commit_out = await _commit_purchase_inbound(client, headers, po=po, uom_map=uom_map)
    event_id = int(commit_out["event_id"])

    r = await client.get(f"/purchase-orders/{po_id}/completion", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, dict), data

    summary = data.get("summary")
    assert isinstance(summary, dict), data
    assert int(summary["po_id"]) == po_id
    assert str(summary["po_no"]) == po_no
    assert int(summary["total_ordered_base"]) == 5
    assert int(summary["total_received_base"]) == 5
    assert int(summary["total_remaining_base"]) == 0
    assert str(summary["completion_status"]) == "RECEIVED"

    lines = data.get("lines")
    assert isinstance(lines, list) and len(lines) == 2, data
    lines_by_line_no = {int(x["line_no"]): x for x in lines}

    line1 = lines_by_line_no[1]
    assert int(line1["item_id"]) == int(item_a)
    assert int(line1["qty_ordered_base"]) == 2
    assert int(line1["qty_received_base"]) == 2
    assert int(line1["qty_remaining_base"]) == 0
    assert str(line1["line_completion_status"]) == "RECEIVED"

    line2 = lines_by_line_no[2]
    assert int(line2["item_id"]) == int(item_b)
    assert int(line2["qty_ordered_base"]) == 3
    assert int(line2["qty_received_base"]) == 3
    assert int(line2["qty_remaining_base"]) == 0
    assert str(line2["line_completion_status"]) == "RECEIVED"

    receipt_events = data.get("receipt_events")
    assert isinstance(receipt_events, list) and len(receipt_events) == 3, data

    event_ids = {int(x["event_id"]) for x in receipt_events}
    assert event_ids == {event_id}, receipt_events

    for ev in receipt_events:
        assert int(ev["po_line_id"]) > 0, ev
        assert int(ev["line_no"]) in (1, 2), ev
        assert str(ev["event_no"]).startswith("IE-"), ev
        assert str(ev["trace_id"]).startswith("IN-COMMIT-"), ev
        assert str(ev["source_ref"]) == po_no, ev

    qty_sum = sum(int(x["qty_base"]) for x in receipt_events)
    assert qty_sum == 5, receipt_events
