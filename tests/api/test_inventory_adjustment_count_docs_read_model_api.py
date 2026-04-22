from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.services.stock_service import StockService


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


async def _pick_enabled_item_with_base_uom(session: AsyncSession) -> dict[str, object]:
    row = (
        await session.execute(
            text(
                """
                SELECT DISTINCT ON (i.id)
                  i.id AS item_id,
                  u.id AS item_uom_id
                FROM items i
                JOIN item_uoms u
                  ON u.item_id = i.id
                WHERE COALESCE(i.enabled, true) = true
                ORDER BY
                  i.id ASC,
                  CASE
                    WHEN COALESCE(u.is_inbound_default, false) THEN 0
                    WHEN COALESCE(u.is_base, false) THEN 1
                    ELSE 2
                  END,
                  u.id ASC
                LIMIT 1
                """
            )
        )
    ).mappings().first()
    assert row is not None, "no enabled item with base uom found"
    return dict(row)


async def _seed_positive_stock(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    qty: int,
    ref: str,
    production_date: date | None = None,
    expiry_date: date | None = None,
) -> None:
    now = datetime.now(UTC)
    prod = production_date or now.date()
    exp = expiry_date or (prod + timedelta(days=365))

    stock = StockService()
    await stock.adjust(
        session=session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        batch_code=str(batch_code),
        delta=int(qty),
        reason="RECEIPT",
        ref=str(ref),
        ref_line=1,
        occurred_at=now,
        production_date=prod,
        expiry_date=exp,
        meta={"sub_reason": "UT_COUNT_DOC_READ_MODEL_SEED"},
    )


async def _create_count_doc(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    warehouse_id: int,
    snapshot_at: datetime,
    remark: str,
) -> dict[str, object]:
    resp = await client.post(
        "/inventory-adjustment/count-docs",
        json={
            "warehouse_id": int(warehouse_id),
            "snapshot_at": snapshot_at.isoformat(),
            "remark": remark,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert int(body["id"]) > 0, body
    return body


@pytest.mark.asyncio
async def test_count_doc_detail_read_model_exposes_posted_summary_and_aggregates(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_item_with_base_uom(session)

    item_id = int(picked["item_id"])
    item_uom_id = int(picked["item_uom_id"])

    code_small = f"UT-CNT-RM-SMALL-{uuid4().hex[:8].upper()}"
    code_big = f"UT-CNT-RM-BIG-{uuid4().hex[:8].upper()}"

    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=code_small,
        qty=5,
        ref=f"ut:count-doc:read-model-seed:{code_small}",
        production_date=date(2030, 1, 1),
        expiry_date=date(2031, 1, 1),
    )
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=code_big,
        qty=7,
        ref=f"ut:count-doc:read-model-seed:{code_big}",
        production_date=date(2030, 2, 1),
        expiry_date=date(2031, 2, 1),
    )
    await session.commit()

    created = await _create_count_doc(
        client,
        headers=headers,
        warehouse_id=warehouse_id,
        snapshot_at=datetime(2030, 1, 9, 8, 0, 0, tzinfo=UTC),
        remark="UT-COUNT-DOC-READMODEL-DETAIL",
    )
    doc_id = int(created["id"])

    r_freeze = await client.post(f"/inventory-adjustment/count-docs/{doc_id}/freeze", headers=headers)
    assert r_freeze.status_code == 200, r_freeze.text

    r_detail0 = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail0.status_code == 200, r_detail0.text
    detail0 = r_detail0.json()
    assert detail0["status"] == "FROZEN", detail0
    assert len(detail0["lines"]) == 1, detail0

    line = detail0["lines"][0]
    assert int(line["snapshot_qty_base"]) == 12, line

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "lines": [
                {
                    "line_id": int(line["id"]),
                    "counted_item_uom_id": item_uom_id,
                    "counted_qty_input": 4,
                    "reason_code": "LOSS",
                    "disposition": "ADJUST",
                    "remark": "ut read model detail",
                }
            ]
        },
        headers=headers,
    )
    assert r_update.status_code == 200, r_update.text
    assert r_update.json()["status"] == "COUNTED", r_update.text

    r_post = await client.post(f"/inventory-adjustment/count-docs/{doc_id}/post", headers=headers)
    assert r_post.status_code == 200, r_post.text
    posted = r_post.json()
    assert posted["status"] == "POSTED", posted

    r_detail = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()

    assert detail["status"] == "POSTED", detail
    assert int(detail["line_count"]) == 1, detail
    assert int(detail["diff_line_count"]) == 1, detail
    assert int(detail["diff_qty_base_total"]) == -8, detail

    assert int(detail["posted_event_id"]) == int(posted["posted_event_id"]), detail
    assert str(detail["posted_event_no"]).startswith("CNT-"), detail
    assert detail["posted_event_type"] == "COUNT", detail
    assert detail["posted_source_type"] == "MANUAL_COUNT", detail
    assert detail["posted_event_kind"] == "COMMIT", detail
    assert detail["posted_event_status"] == "COMMITTED", detail

    assert len(detail["lines"]) == 1, detail
    dline = detail["lines"][0]
    assert int(dline["diff_qty_base"]) == -8, dline
    assert dline["reason_code"] == "LOSS", dline
    assert dline["disposition"] == "ADJUST", dline
    assert len(dline["lot_snapshots"]) == 2, dline


@pytest.mark.asyncio
async def test_count_doc_list_read_model_exposes_aggregates_and_posted_summary(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_item_with_base_uom(session)

    item_id = int(picked["item_id"])
    item_uom_id = int(picked["item_uom_id"])

    batch_code = f"UT-CNT-RM-LIST-{uuid4().hex[:8].upper()}"
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
        qty=5,
        ref=f"ut:count-doc:list-read-model-seed:{batch_code}",
    )
    await session.commit()

    created = await _create_count_doc(
        client,
        headers=headers,
        warehouse_id=warehouse_id,
        snapshot_at=datetime(2030, 1, 10, 8, 0, 0, tzinfo=UTC),
        remark="UT-COUNT-DOC-READMODEL-LIST",
    )
    doc_id = int(created["id"])

    r_freeze = await client.post(f"/inventory-adjustment/count-docs/{doc_id}/freeze", headers=headers)
    assert r_freeze.status_code == 200, r_freeze.text

    r_detail0 = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail0.status_code == 200, r_detail0.text
    detail0 = r_detail0.json()
    assert len(detail0["lines"]) == 1, detail0
    line = detail0["lines"][0]
    assert int(line["snapshot_qty_base"]) == 5, line

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "lines": [
                {
                    "line_id": int(line["id"]),
                    "counted_item_uom_id": item_uom_id,
                    "counted_qty_input": 5,
                    "reason_code": "MATCHED",
                    "disposition": "KEEP",
                    "remark": "ut read model list",
                }
            ]
        },
        headers=headers,
    )
    assert r_update.status_code == 200, r_update.text
    assert r_update.json()["status"] == "COUNTED", r_update.text

    r_post = await client.post(f"/inventory-adjustment/count-docs/{doc_id}/post", headers=headers)
    assert r_post.status_code == 200, r_post.text
    posted = r_post.json()
    assert posted["status"] == "POSTED", posted

    r_list = await client.get(
        "/inventory-adjustment/count-docs",
        params={"warehouse_id": warehouse_id, "limit": 50, "offset": 0},
        headers=headers,
    )
    assert r_list.status_code == 200, r_list.text
    listed = r_list.json()

    row = next((x for x in listed["items"] if int(x["id"]) == doc_id), None)
    assert row is not None, listed

    assert row["status"] == "POSTED", row
    assert int(row["line_count"]) == 1, row
    assert int(row["diff_line_count"]) == 0, row
    assert int(row["diff_qty_base_total"]) == 0, row

    assert int(row["posted_event_id"]) == int(posted["posted_event_id"]), row
    assert str(row["posted_event_no"]).startswith("CNT-"), row
    assert row["posted_event_type"] == "COUNT", row
    assert row["posted_source_type"] == "MANUAL_COUNT", row
    assert row["posted_event_kind"] == "COMMIT", row
    assert row["posted_event_status"] == "COMMITTED", row
