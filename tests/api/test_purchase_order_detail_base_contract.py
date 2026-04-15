# tests/api/test_purchase_order_detail_base_contract.py
from __future__ import annotations

from typing import Any, Dict
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


def _assert_po_head_contract(detail: Dict[str, Any]) -> None:
    assert "id" in detail, detail
    assert isinstance(detail["id"], int), detail

    assert "po_no" in detail, detail
    po_no = str(detail.get("po_no") or "").strip()
    assert po_no, detail
    assert po_no.startswith("PO-"), detail

    assert "supplier_id" in detail, detail
    assert "supplier_name" in detail, detail
    assert isinstance(detail["supplier_id"], int), detail
    assert str(detail["supplier_name"]).strip(), detail


def _assert_line_plan_contract(line: Dict[str, Any]) -> None:
    # 计划合同：只看计划字段，不再混入执行态字段
    for k in ("qty_ordered_base", "qty_ordered_input", "purchase_ratio_to_base_snapshot"):
        assert k in line, line
        assert isinstance(line[k], int), line

    ordered_base = int(line["qty_ordered_base"])
    qty_input = int(line["qty_ordered_input"])
    ratio = int(line["purchase_ratio_to_base_snapshot"])

    assert ordered_base >= 0
    assert qty_input > 0
    assert ratio >= 1
    assert ordered_base == qty_input * ratio, line

    assert "qty_received_base" not in line, line
    assert "qty_remaining_base" not in line, line


def _assert_line_snapshot_contract(line: Dict[str, Any]) -> None:
    assert "item_name" in line, line
    assert "item_sku" in line, line

    name = (line.get("item_name") or "").strip()
    sku = (line.get("item_sku") or "").strip()

    assert name, f"item_name must be non-empty (backend-generated snapshot), line={line}"
    assert sku, f"item_sku must be non-empty (backend-generated snapshot), line={line}"


@pytest.mark.asyncio
async def test_purchase_order_detail_plan_contract(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    item_id = await _insert_item_internal_none(session, sku_prefix="UT-PLAN-DETAIL")
    await session.commit()

    uom_id = await _pick_any_uom_id(session, item_id=item_id)

    payload = {
        "supplier_id": 1,
        "warehouse_id": 1,
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [
            {"line_no": 1, "item_id": int(item_id), "uom_id": int(uom_id), "qty_input": 2},
        ],
    }

    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    po = r.json()
    assert isinstance(po, dict), po

    po_id = int(po.get("id") or 0)
    assert po_id > 0, po

    r2 = await client.get(f"/purchase-orders/{po_id}", headers=headers)
    assert r2.status_code == 200, r2.text
    detail = r2.json()
    assert isinstance(detail, dict), detail

    _assert_po_head_contract(detail)

    lines = detail.get("lines")
    assert isinstance(lines, list) and lines, detail

    for ln in lines:
        assert isinstance(ln, dict), ln
        _assert_line_plan_contract(ln)
        _assert_line_snapshot_contract(ln)
