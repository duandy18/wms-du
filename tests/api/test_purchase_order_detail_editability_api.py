# tests/api/test_purchase_order_detail_editability_api.py
from __future__ import annotations

from typing import Any, Dict
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


async def _create_po_one_line(
    session: AsyncSession,
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    *,
    item_id: int,
) -> Dict[str, Any]:
    uom_id = await _pick_any_uom_id(session, item_id=int(item_id))
    payload = {
        "warehouse_id": 1,
        "supplier_id": 1,
        "purchaser": "UT",
        "purchase_time": "2026-01-14T10:00:00Z",
        "lines": [
            {"line_no": 1, "item_id": int(item_id), "uom_id": int(uom_id), "qty_input": 2},
        ],
    }
    r = await client.post("/purchase-orders/", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, dict), data
    return data


async def _commit_purchase_inbound(
    client: httpx.AsyncClient,
    headers: Dict[str, str],
    *,
    po: Dict[str, Any],
    uom_id: int,
) -> Dict[str, Any]:
    po_no = str(po["po_no"])
    line = po["lines"][0]

    payload = {
        "warehouse_id": 1,
        "source_type": "PURCHASE_ORDER",
        "source_ref": po_no,
        "occurred_at": "2026-01-14T10:30:00Z",
        "remark": f"editability test for po_no={po_no}",
        "lines": [
            {
                "item_id": int(line["item_id"]),
                "uom_id": int(uom_id),
                "qty_input": 1,
                "po_line_id": int(line["id"]),
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
async def test_purchase_order_detail_returns_editable_true_when_clean(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    item_id = await _insert_item_internal_none(session, sku_prefix="UT-EDITABLE-CLEAN")
    await session.commit()

    po = await _create_po_one_line(session, client, headers, item_id=int(item_id))
    po_id = int(po["id"])

    r = await client.get(f"/purchase-orders/{po_id}", headers=headers)
    assert r.status_code == 200, r.text
    detail = r.json()

    assert detail["editable"] is True, detail
    assert detail["edit_block_reason"] is None, detail


@pytest.mark.asyncio
async def test_purchase_order_detail_returns_not_editable_when_committed_inbound_exists(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)

    item_id = await _insert_item_internal_none(session, sku_prefix="UT-EDITABLE-COMMIT")
    await session.commit()

    po = await _create_po_one_line(session, client, headers, item_id=int(item_id))
    po_id = int(po["id"])
    uom_id = await _pick_any_uom_id(session, item_id=int(item_id))

    await _commit_purchase_inbound(client, headers, po=po, uom_id=int(uom_id))

    r = await client.get(f"/purchase-orders/{po_id}", headers=headers)
    assert r.status_code == 200, r.text
    detail = r.json()

    assert detail["editable"] is False, detail
    assert "正式采购入库事实" in str(detail["edit_block_reason"] or ""), detail
