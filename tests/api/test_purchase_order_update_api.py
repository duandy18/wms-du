# tests/api/test_purchase_order_update_api.py
from __future__ import annotations

from typing import Any, Dict, Tuple
from uuid import uuid4

import httpx
import pytest
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
    po_no = str(po["po_no"])
    lines = list(po["lines"])
    by_line_no = {int(x["line_no"]): x for x in lines}

    payload = {
        "warehouse_id": 1,
        "source_type": "PURCHASE_ORDER",
        "source_ref": po_no,
        "occurred_at": "2026-01-14T10:30:00Z",
        "remark": f"update test for po_no={po_no}",
        "lines": [
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
    return out


@pytest.mark.asyncio
async def test_purchase_order_update_replaces_head_and_lines_and_rebuilds_completion(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    item_a = await _insert_item_internal_none(session, sku_prefix="UT-UPD-A")
    item_b = await _insert_item_internal_none(session, sku_prefix="UT-UPD-B")
    item_c = await _insert_item_internal_none(session, sku_prefix="UT-UPD-C")
    await session.commit()

    created, _ = await _create_po_two_lines(session, client, headers, (item_a, item_b))
    po_id = int(created["id"])
    po_no = str(created["po_no"])

    uom_b = await _pick_any_uom_id(session, item_id=int(item_b))
    uom_c = await _pick_any_uom_id(session, item_id=int(item_c))

    update_payload = {
        "supplier_id": 1,
        "warehouse_id": 1,
        "purchaser": "UT-UPDATED",
        "purchase_time": "2026-01-15T09:45:00Z",
        "remark": "updated-by-put",
        "lines": [
            {
                "line_no": 1,
                "item_id": int(item_b),
                "uom_id": int(uom_b),
                "qty_input": 4,
                "supply_price": "2.50",
                "discount_amount": "1.50",
                "discount_note": "L1-DISCOUNT",
                "remark": "LINE-1-UPDATED",
            },
            {
                "line_no": 2,
                "item_id": int(item_c),
                "uom_id": int(uom_c),
                "qty_input": 5,
                "supply_price": "1.00",
                "discount_amount": "0.50",
                "discount_note": "L2-DISCOUNT",
                "remark": "LINE-2-UPDATED",
            },
        ],
    }

    r = await client.put(f"/purchase-orders/{po_id}", json=update_payload, headers=headers)
    assert r.status_code == 200, r.text
    updated = r.json()
    assert isinstance(updated, dict), updated

    assert int(updated["id"]) == po_id
    assert str(updated["po_no"]) == po_no
    assert str(updated["purchaser"]) == "UT-UPDATED"
    assert str(updated["remark"]) == "updated-by-put"
    assert str(updated["status"]) == "CREATED"

    lines = updated.get("lines")
    assert isinstance(lines, list) and len(lines) == 2, updated
    lines_by_no = {int(x["line_no"]): x for x in lines}

    line1 = lines_by_no[1]
    assert int(line1["item_id"]) == int(item_b), line1
    assert int(line1["qty_ordered_input"]) == 4, line1
    assert int(line1["qty_ordered_base"]) == 4, line1
    assert str(line1["discount_note"]) == "L1-DISCOUNT", line1
    assert str(line1["remark"]) == "LINE-1-UPDATED", line1

    line2 = lines_by_no[2]
    assert int(line2["item_id"]) == int(item_c), line2
    assert int(line2["qty_ordered_input"]) == 5, line2
    assert int(line2["qty_ordered_base"]) == 5, line2
    assert str(line2["discount_note"]) == "L2-DISCOUNT", line2
    assert str(line2["remark"]) == "LINE-2-UPDATED", line2

    old_item_ids = {int(item_a)}
    returned_item_ids = {int(x["item_id"]) for x in lines}
    assert returned_item_ids.isdisjoint(old_item_ids), updated

    r2 = await client.get(f"/purchase-orders/{po_id}/completion", headers=headers)
    assert r2.status_code == 200, r2.text
    detail = r2.json()

    comp_lines = detail.get("lines")
    assert isinstance(comp_lines, list) and len(comp_lines) == 2, detail
    comp_by_no = {int(x["line_no"]): x for x in comp_lines}

    c1 = comp_by_no[1]
    assert int(c1["item_id"]) == int(item_b), c1
    assert int(c1["qty_ordered_base"]) == 4, c1
    assert int(c1["qty_received_base"]) == 0, c1
    assert int(c1["qty_remaining_base"]) == 4, c1
    assert str(c1["line_completion_status"]) == "NOT_RECEIVED", c1

    c2 = comp_by_no[2]
    assert int(c2["item_id"]) == int(item_c), c2
    assert int(c2["qty_ordered_base"]) == 5, c2
    assert int(c2["qty_received_base"]) == 0, c2
    assert int(c2["qty_remaining_base"]) == 5, c2
    assert str(c2["line_completion_status"]) == "NOT_RECEIVED", c2


@pytest.mark.asyncio
async def test_purchase_order_update_rejects_when_committed_inbound_exists(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    item_a = await _insert_item_internal_none(session, sku_prefix="UT-UPD-COMMIT-A")
    item_b = await _insert_item_internal_none(session, sku_prefix="UT-UPD-COMMIT-B")
    item_c = await _insert_item_internal_none(session, sku_prefix="UT-UPD-COMMIT-C")
    await session.commit()

    created, uom_map = await _create_po_two_lines(session, client, headers, (item_a, item_b))
    po_id = int(created["id"])

    await _commit_purchase_inbound(client, headers, po=created, uom_map=uom_map)

    uom_c = await _pick_any_uom_id(session, item_id=int(item_c))
    payload = {
        "supplier_id": 1,
        "warehouse_id": 1,
        "purchaser": "UT-COMMIT-BLOCK",
        "purchase_time": "2026-01-16T12:00:00Z",
        "remark": "should-block-after-commit",
        "lines": [
            {
                "line_no": 1,
                "item_id": int(item_c),
                "uom_id": int(uom_c),
                "qty_input": 9,
            }
        ],
    }

    r = await client.put(f"/purchase-orders/{po_id}", json=payload, headers=headers)
    assert r.status_code == 409, r.text
    assert "正式采购入库事实" in r.text, r.text


@pytest.mark.asyncio
async def test_purchase_order_update_rejects_when_status_not_created(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    item_a = await _insert_item_internal_none(session, sku_prefix="UT-UPD-CLOSE-A")
    item_b = await _insert_item_internal_none(session, sku_prefix="UT-UPD-CLOSE-B")
    await session.commit()

    created, _ = await _create_po_two_lines(session, client, headers, (item_a, item_b))
    po_id = int(created["id"])

    r_close = await client.post(
        f"/purchase-orders/{po_id}/close",
        json={"note": "close-before-update"},
        headers=headers,
    )
    assert r_close.status_code == 200, r_close.text

    uom_a = await _pick_any_uom_id(session, item_id=int(item_a))
    payload = {
        "supplier_id": 1,
        "warehouse_id": 1,
        "purchaser": "UT-CLOSED-BLOCK",
        "purchase_time": "2026-01-16T14:00:00Z",
        "lines": [
            {
                "line_no": 1,
                "item_id": int(item_a),
                "uom_id": int(uom_a),
                "qty_input": 7,
            }
        ],
    }

    r = await client.put(f"/purchase-orders/{po_id}", json=payload, headers=headers)
    assert r.status_code == 409, r.text
    assert "状态不允许编辑" in r.text, r.text
