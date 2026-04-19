from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.services._helpers import ensure_store

pytestmark = pytest.mark.asyncio


async def _login_admin_headers(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _ensure_warehouse(session: AsyncSession, warehouse_id: int = 1) -> int:
    await session.execute(
        text(
            """
            INSERT INTO warehouses (id, name)
            VALUES (:id, :name)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": int(warehouse_id), "name": f"WH-{warehouse_id}"},
    )
    await session.commit()
    return int(warehouse_id)


async def _pick_any_item_id(session: AsyncSession) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT id
                FROM items
                ORDER BY id ASC
                LIMIT 1
                """
            )
        )
    ).first()
    assert row is not None
    return int(row[0])


async def _seed_order_event(session: AsyncSession, warehouse_id: int) -> int:
    uniq = uuid4().hex[:8]
    item_id = await _pick_any_item_id(session)

    store_id = await ensure_store(
        session,
        platform="PDD",
        shop_id="1",
        name="UT-STORE",
    )

    row = await session.execute(
        text(
            """
            INSERT INTO orders (
              platform, shop_id, store_id, ext_order_no, status, created_at, updated_at
            )
            VALUES (
              'PDD', '1', :store_id, :ext_order_no, 'CREATED', now(), now()
            )
            RETURNING id
            """
        ),
        {"store_id": int(store_id), "ext_order_no": f"SUM-ORD-{uniq}"},
    )
    order_id = int(row.scalar_one())

    row2 = await session.execute(
        text(
            """
            INSERT INTO order_lines (order_id, item_id, req_qty)
            VALUES (:order_id, :item_id, 2)
            RETURNING id
            """
        ),
        {"order_id": int(order_id), "item_id": int(item_id)},
    )
    order_line_id = int(row2.scalar_one())

    row3 = await session.execute(
        text(
            """
            INSERT INTO wms_events (
              event_no, warehouse_id, source_type, source_ref,
              occurred_at, trace_id, event_kind, status, created_by, remark, event_type
            )
            VALUES (
              :event_no, :warehouse_id, 'ORDER', :source_ref,
              now(), :trace_id, 'COMMIT', 'COMMITTED', NULL, 'order summary', 'OUTBOUND'
            )
            RETURNING id
            """
        ),
        {
            "event_no": f"OUT-SUM-ORD-{uniq}",
            "warehouse_id": int(warehouse_id),
            "source_ref": f"ORD:PDD:1:SUM-ORD-{uniq}",
            "trace_id": f"TRC-SUM-ORD-{uniq}",
        },
    )
    event_id = int(row3.scalar_one())

    await session.execute(
        text(
            """
            INSERT INTO outbound_event_lines (
              event_id, ref_line, item_id, qty_outbound, lot_id,
              lot_code_snapshot, order_line_id, manual_doc_line_id,
              item_name_snapshot, item_spec_snapshot, remark
            )
            VALUES (
              :event_id, 1, :item_id, 2, 1,
              NULL, :order_line_id, NULL,
              NULL, NULL, 'order line'
            )
            """
        ),
        {
            "event_id": int(event_id),
            "item_id": int(item_id),
            "order_line_id": int(order_line_id),
        },
    )
    await session.commit()
    return int(event_id)


async def _seed_manual_event(session: AsyncSession, warehouse_id: int) -> int:
    uniq = uuid4().hex[:8]
    item_id = await _pick_any_item_id(session)

    row = await session.execute(
        text(
            """
            INSERT INTO manual_outbound_docs (
              warehouse_id, doc_no, doc_type, status, recipient_name, created_at
            )
            VALUES (
              :warehouse_id, :doc_no, 'MANUAL_OUTBOUND', 'RELEASED', '张三', now()
            )
            RETURNING id
            """
        ),
        {
            "warehouse_id": int(warehouse_id),
            "doc_no": f"MOB-SUM-{uniq}",
        },
    )
    doc_id = int(row.scalar_one())

    row2 = await session.execute(
        text(
            """
            INSERT INTO manual_outbound_lines (
              doc_id, line_no, item_id, requested_qty, note
            )
            VALUES (
              :doc_id, 1, :item_id, 1, 'manual line'
            )
            RETURNING id
            """
        ),
        {
            "doc_id": int(doc_id),
            "item_id": int(item_id),
        },
    )
    doc_line_id = int(row2.scalar_one())

    row3 = await session.execute(
        text(
            """
            INSERT INTO wms_events (
              event_no, warehouse_id, source_type, source_ref,
              occurred_at, trace_id, event_kind, status, created_by, remark, event_type
            )
            VALUES (
              :event_no, :warehouse_id, 'MANUAL', :source_ref,
              now(), :trace_id, 'COMMIT', 'COMMITTED', NULL, 'manual summary', 'OUTBOUND'
            )
            RETURNING id
            """
        ),
        {
            "event_no": f"OUT-SUM-MAN-{uniq}",
            "warehouse_id": int(warehouse_id),
            "source_ref": f"MOB-SUM-{uniq}",
            "trace_id": f"TRC-SUM-MAN-{uniq}",
        },
    )
    event_id = int(row3.scalar_one())

    await session.execute(
        text(
            """
            INSERT INTO outbound_event_lines (
              event_id, ref_line, item_id, qty_outbound, lot_id,
              lot_code_snapshot, order_line_id, manual_doc_line_id,
              item_name_snapshot, item_spec_snapshot, remark
            )
            VALUES (
              :event_id, 1, :item_id, 1, 1,
              NULL, NULL, :manual_doc_line_id,
              NULL, NULL, 'manual line'
            )
            """
        ),
        {
            "event_id": int(event_id),
            "item_id": int(item_id),
            "manual_doc_line_id": int(doc_line_id),
        },
    )
    await session.commit()
    return int(event_id)


async def test_outbound_summary_list_and_detail(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _ensure_warehouse(session, 1)

    order_event_id = await _seed_order_event(session, warehouse_id)
    manual_event_id = await _seed_manual_event(session, warehouse_id)

    resp = await client.get("/wms/outbound/summary?limit=20&offset=0", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "items" in data
    assert isinstance(data["items"], list)
    ids = {int(x["event_id"]) for x in data["items"]}
    assert order_event_id in ids
    assert manual_event_id in ids

    order_rows = [x for x in data["items"] if int(x["event_id"]) == order_event_id]
    assert len(order_rows) == 1
    assert order_rows[0]["source_type"] == "ORDER"
    assert order_rows[0]["lines_count"] == 1
    assert order_rows[0]["total_qty_outbound"] == 2

    resp2 = await client.get(f"/wms/outbound/summary/{manual_event_id}", headers=headers)
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()

    assert int(data2["event"]["event_id"]) == manual_event_id
    assert data2["event"]["source_type"] == "MANUAL"
    assert len(data2["lines"]) == 1
    assert data2["lines"][0]["manual_doc_line_id"] is not None
