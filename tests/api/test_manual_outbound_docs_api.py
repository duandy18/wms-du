from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


pytestmark = pytest.mark.asyncio


async def _login_admin_headers(client: AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


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
    assert row is not None, "expected at least one item in baseline"
    return int(row[0])


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


async def test_manual_outbound_docs_create_release_void(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _ensure_warehouse(session, 1)
    item_id = await _pick_any_item_id(session)

    # 1) create
    resp = await client.post(
        "/wms/outbound/manual-docs",
        headers=headers,
        json={
            "warehouse_id": warehouse_id,
            "doc_type": "MANUAL_OUTBOUND",
            "recipient_name": f"张三-{uuid4().hex[:6]}",
            "recipient_type": "EMPLOYEE",
            "recipient_note": "测试领用",
            "remark": "整单备注",
            "lines": [
                {
                    "item_id": item_id,
                    "requested_qty": 2,
                    "remark": "行备注"
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "DRAFT"
    assert data["warehouse_id"] == warehouse_id
    assert data["doc_type"] == "MANUAL_OUTBOUND"
    assert len(data["lines"]) == 1
    doc_id = int(data["id"])

    # 2) get detail
    resp2 = await client.get(
        f"/wms/outbound/manual-docs/{doc_id}",
        headers=headers,
    )
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2["id"] == doc_id
    assert data2["status"] == "DRAFT"
    assert len(data2["lines"]) == 1
    assert int(data2["lines"][0]["item_id"]) == item_id
    assert int(data2["lines"][0]["requested_qty"]) == 2

    # 3) release
    resp3 = await client.post(
        f"/wms/outbound/manual-docs/{doc_id}/release",
        headers=headers,
    )
    assert resp3.status_code == 200, resp3.text
    data3 = resp3.json()
    assert data3["id"] == doc_id
    assert data3["status"] == "RELEASED"

    # 4) list
    resp4 = await client.get(
        "/wms/outbound/manual-docs?limit=20&offset=0",
        headers=headers,
    )
    assert resp4.status_code == 200, resp4.text
    items = resp4.json()
    assert isinstance(items, list)
    assert any(int(x["id"]) == doc_id for x in items)

    # 5) void
    resp5 = await client.post(
        f"/wms/outbound/manual-docs/{doc_id}/void",
        headers=headers,
    )
    assert resp5.status_code == 200, resp5.text
    data5 = resp5.json()
    assert data5["id"] == doc_id
    assert data5["status"] == "VOIDED"

    # 6) DB evidence
    row = (
        await session.execute(
            text(
                """
                SELECT status
                FROM manual_outbound_docs
                WHERE id = :doc_id
                LIMIT 1
                """
            ),
            {"doc_id": doc_id},
        )
    ).first()
    assert row is not None
    assert row[0] == "VOIDED"
