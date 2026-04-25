from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.utils.ensure_minimal import set_stock_qty

pytestmark = pytest.mark.asyncio
UTC = timezone.utc


async def _login_admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post("/users/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _pick_active_warehouse_id(session: AsyncSession) -> int:
    row = await session.execute(
        text(
            """
            SELECT id
              FROM warehouses
             WHERE COALESCE(active, true) = true
             ORDER BY id
             LIMIT 1
            """
        )
    )
    wid = row.scalar_one_or_none()
    assert wid is not None, "no active warehouse found"
    return int(wid)


async def _pick_enabled_item(session: AsyncSession) -> dict[str, object]:
    row = await session.execute(
        text(
            """
            SELECT DISTINCT ON (i.id)
              i.id AS item_id,
              i.name AS item_name,
              i.spec AS item_spec
            FROM items i
            JOIN item_uoms u
              ON u.item_id = i.id
            WHERE COALESCE(i.enabled, true) = true
            ORDER BY i.id ASC, u.id ASC
            LIMIT 1
            """
        )
    )
    item = row.mappings().first()
    assert item is not None, "no enabled item found"
    return dict(item)


async def _seed_positive_stock(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    qty: int,
    ref: str,
) -> None:
    _ = ref
    await set_stock_qty(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=str(batch_code),
        qty=int(qty),
    )


@pytest.mark.asyncio
async def test_count_doc_execution_detail_is_slim_for_execution_page(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    item = await _pick_enabled_item(session)

    batch_code = f"UT-CNT-EXEC-{uuid4().hex[:8].upper()}"
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        batch_code=batch_code,
        qty=5,
        ref=f"ut:count-doc:execution-seed:{batch_code}",
    )
    await session.commit()

    r_create = await client.post(
        "/inventory-adjustment/count-docs",
        json={
            "warehouse_id": warehouse_id,
            "snapshot_at": datetime(2030, 1, 9, 8, 0, 0, tzinfo=UTC).isoformat(),
            "remark": "UT-COUNT-DOC-EXECUTION",
        },
        headers=headers,
    )
    assert r_create.status_code == 201, r_create.text
    created = r_create.json()
    doc_id = int(created["id"])

    r_freeze = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/freeze",
        headers=headers,
    )
    assert r_freeze.status_code == 200, r_freeze.text

    r_execution0 = await client.get(
        f"/inventory-adjustment/count-docs/{doc_id}/execution",
        headers=headers,
    )
    assert r_execution0.status_code == 200, r_execution0.text
    execution0 = r_execution0.json()
    assert len(execution0["lines"]) == 1, execution0
    line_id = int(execution0["lines"][0]["id"])
    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "counted_by_name_snapshot": "张三",
            "lines": [
                {
                    "line_id": line_id,
                    "counted_qty_input": 5,
                }
            ],
        },
        headers=headers,
    )
    assert r_update.status_code == 200, r_update.text

    r_post = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/post",
        json={"reviewed_by_name_snapshot": "李四"},
        headers=headers,
    )
    assert r_post.status_code == 200, r_post.text

    r_execution = await client.get(
        f"/inventory-adjustment/count-docs/{doc_id}/execution",
        headers=headers,
    )
    assert r_execution.status_code == 200, r_execution.text
    execution = r_execution.json()

    assert int(execution["id"]) == doc_id, execution
    assert execution["status"] == "POSTED", execution
    assert execution["counted_by_name_snapshot"] == "张三", execution
    assert execution["reviewed_by_name_snapshot"] == "李四", execution
    assert int(execution["line_count"]) == 1, execution

    assert len(execution["lines"]) == 1, execution
    line = execution["lines"][0]

    assert int(line["id"]) == line_id, line
    assert int(line["snapshot_qty_base"]) == 5, line
    assert int(line["counted_qty_input"]) == 5, line
    assert int(line["counted_qty_base"]) == 5, line
    assert int(line["diff_qty_base"]) == 0, line
    assert line["base_uom_name"], line

    assert "reason_code" not in line, line
    assert "disposition" not in line, line
    assert "remark" not in line, line
    assert "lot_snapshots" not in line, line
