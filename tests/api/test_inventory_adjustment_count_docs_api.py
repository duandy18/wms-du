from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.services.stock_service import StockService
from app.wms.snapshot.services.snapshot_run import run_snapshot
from app.wms.reconciliation.services.three_books_consistency import verify_commit_three_books


pytestmark = pytest.mark.asyncio
UTC = timezone.utc


def _norm_utc_iso(v: str) -> str:
    return str(v).replace("Z", "+00:00")


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


async def _pick_enabled_items_with_base_uom(
    session: AsyncSession,
    *,
    limit: int,
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT ON (i.id)
                  i.id AS item_id,
                  i.name AS item_name,
                  i.spec AS item_spec,
                  u.id AS item_uom_id,
                  COALESCE(NULLIF(u.display_name, ''), u.uom) AS uom_name,
                  u.ratio_to_base AS ratio_to_base
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
                """
            )
        )
    ).mappings().all()

    items = [dict(x) for x in rows[:limit]]
    assert len(items) >= limit, f"need at least {limit} enabled items with item_uoms"
    return items


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
        meta={"sub_reason": "UT_COUNT_DOC_STOCK_SEED"},
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
async def test_count_doc_create_list_detail_contract(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    snapshot_at = datetime(2030, 1, 1, 8, 0, 0, tzinfo=UTC)

    created = await _create_count_doc(
        client,
        headers=headers,
        warehouse_id=warehouse_id,
        snapshot_at=snapshot_at,
        remark="UT-COUNT-DOC-CREATE",
    )

    assert created["status"] == "DRAFT", created
    assert created["warehouse_id"] == int(warehouse_id), created
    assert created["posted_event_id"] is None, created
    assert created["counted_at"] is None, created
    assert created["posted_at"] is None, created
    assert str(created["count_no"]).startswith("CTD-"), created

    doc_id = int(created["id"])

    r_detail = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()

    assert int(detail["id"]) == doc_id, detail
    assert detail["status"] == "DRAFT", detail
    assert detail["warehouse_id"] == int(warehouse_id), detail
    assert _norm_utc_iso(detail["snapshot_at"]) == snapshot_at.isoformat(), detail
    assert detail["lines"] == [], detail

    r_list = await client.get(
        "/inventory-adjustment/count-docs",
        params={"warehouse_id": warehouse_id, "limit": 50, "offset": 0},
        headers=headers,
    )
    assert r_list.status_code == 200, r_list.text
    listed = r_list.json()

    assert int(listed["total"]) >= 1, listed
    assert any(int(x["id"]) == doc_id for x in listed["items"]), listed


@pytest.mark.asyncio
async def test_count_doc_freeze_generates_item_lines_and_lot_snapshots(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_items_with_base_uom(session, limit=2)

    item_a = picked[0]
    item_b = picked[1]

    code_a1 = f"UT-CNT-A1-{uuid4().hex[:8].upper()}"
    code_a2 = f"UT-CNT-A2-{uuid4().hex[:8].upper()}"
    code_b1 = f"UT-CNT-B1-{uuid4().hex[:8].upper()}"

    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item_a["item_id"]),
        batch_code=code_a1,
        qty=5,
        ref=f"ut:count-doc:seed:{code_a1}",
    )
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item_a["item_id"]),
        batch_code=code_a2,
        qty=7,
        ref=f"ut:count-doc:seed:{code_a2}",
    )
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item_b["item_id"]),
        batch_code=code_b1,
        qty=3,
        ref=f"ut:count-doc:seed:{code_b1}",
    )
    await session.commit()

    created = await _create_count_doc(
        client,
        headers=headers,
        warehouse_id=warehouse_id,
        snapshot_at=datetime(2030, 1, 2, 8, 0, 0, tzinfo=UTC),
        remark="UT-COUNT-DOC-FREEZE",
    )
    doc_id = int(created["id"])

    r_freeze = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/freeze",
        headers=headers,
    )
    assert r_freeze.status_code == 200, r_freeze.text
    frozen = r_freeze.json()

    assert int(frozen["doc_id"]) == doc_id, frozen
    assert frozen["status"] == "FROZEN", frozen
    assert int(frozen["line_count"]) == 2, frozen
    assert int(frozen["lot_snapshot_count"]) >= 2, frozen

    r_detail = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()

    assert detail["status"] == "FROZEN", detail
    assert len(detail["lines"]) == 2, detail

    total_lot_snapshots = sum(len(x["lot_snapshots"]) for x in detail["lines"])
    assert total_lot_snapshots == int(frozen["lot_snapshot_count"]), detail

    lines_by_item = {int(x["item_id"]): x for x in detail["lines"]}
    assert set(lines_by_item.keys()) == {int(item_a["item_id"]), int(item_b["item_id"])}, detail

    line_a = lines_by_item[int(item_a["item_id"])]
    assert int(line_a["snapshot_qty_base"]) == 12, line_a
    assert len(line_a["lot_snapshots"]) >= 1, line_a
    assert sum(int(x["snapshot_qty_base"]) for x in line_a["lot_snapshots"]) == 12, line_a

    line_b = lines_by_item[int(item_b["item_id"])]
    assert int(line_b["snapshot_qty_base"]) == 3, line_b
    assert len(line_b["lot_snapshots"]) >= 1, line_b
    assert sum(int(x["snapshot_qty_base"]) for x in line_b["lot_snapshots"]) == 3, line_b


@pytest.mark.asyncio
async def test_count_doc_update_lines_auto_marks_counted(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_items_with_base_uom(session, limit=2)

    item_a = picked[0]
    item_b = picked[1]

    code_a1 = f"UT-CNT-UPD-A1-{uuid4().hex[:8].upper()}"
    code_b1 = f"UT-CNT-UPD-B1-{uuid4().hex[:8].upper()}"

    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item_a["item_id"]),
        batch_code=code_a1,
        qty=4,
        ref=f"ut:count-doc:update-seed:{code_a1}",
    )
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item_b["item_id"]),
        batch_code=code_b1,
        qty=2,
        ref=f"ut:count-doc:update-seed:{code_b1}",
    )
    await session.commit()

    created = await _create_count_doc(
        client,
        headers=headers,
        warehouse_id=warehouse_id,
        snapshot_at=datetime(2030, 1, 3, 8, 0, 0, tzinfo=UTC),
        remark="UT-COUNT-DOC-UPDATE",
    )
    doc_id = int(created["id"])

    r_freeze = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/freeze",
        headers=headers,
    )
    assert r_freeze.status_code == 200, r_freeze.text

    r_detail = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()
    assert detail["status"] == "FROZEN", detail
    assert len(detail["lines"]) == 2, detail

    uom_map = {
        int(item_a["item_id"]): {
            "item_uom_id": int(item_a["item_uom_id"]),
            "ratio_to_base": int(item_a["ratio_to_base"]),
        },
        int(item_b["item_id"]): {
            "item_uom_id": int(item_b["item_uom_id"]),
            "ratio_to_base": int(item_b["ratio_to_base"]),
        },
    }

    update_lines: list[dict[str, object]] = []
    for line in detail["lines"]:
        item_id = int(line["item_id"])
        snapshot_qty_base = int(line["snapshot_qty_base"])
        cfg = uom_map[item_id]
        if item_id == int(item_a["item_id"]):
            counted_qty_input = snapshot_qty_base
            reason_code = "MATCHED"
            disposition = "KEEP"
            remark = "ut matched"
        else:
            counted_qty_input = snapshot_qty_base - 1
            reason_code = "LOSS"
            disposition = "ADJUST"
            remark = "ut diff"

        update_lines.append(
            {
                "line_id": int(line["id"]),
                "counted_item_uom_id": int(cfg["item_uom_id"]),
                "counted_qty_input": int(counted_qty_input),
                "reason_code": reason_code,
                "disposition": disposition,
                "remark": remark,
            }
        )

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={"lines": update_lines},
        headers=headers,
    )
    assert r_update.status_code == 200, r_update.text
    updated = r_update.json()

    assert int(updated["doc_id"]) == doc_id, updated
    assert updated["status"] == "COUNTED", updated
    assert int(updated["updated_count"]) == 2, updated
    assert len(updated["lines"]) == 2, updated

    lines_by_item = {int(x["item_id"]): x for x in updated["lines"]}

    line_a = lines_by_item[int(item_a["item_id"])]
    assert int(line_a["counted_item_uom_id"]) == int(item_a["item_uom_id"]), line_a
    assert int(line_a["counted_ratio_to_base_snapshot"]) == int(item_a["ratio_to_base"]), line_a
    assert int(line_a["counted_qty_input"]) == 4, line_a
    assert int(line_a["counted_qty_base"]) == 4, line_a
    assert int(line_a["diff_qty_base"]) == 0, line_a
    assert line_a["reason_code"] == "MATCHED", line_a
    assert line_a["disposition"] == "KEEP", line_a

    line_b = lines_by_item[int(item_b["item_id"])]
    assert int(line_b["counted_item_uom_id"]) == int(item_b["item_uom_id"]), line_b
    assert int(line_b["counted_ratio_to_base_snapshot"]) == int(item_b["ratio_to_base"]), line_b
    assert int(line_b["counted_qty_input"]) == 1, line_b
    assert int(line_b["counted_qty_base"]) == 1, line_b
    assert int(line_b["diff_qty_base"]) == -1, line_b
    assert line_b["reason_code"] == "LOSS", line_b
    assert line_b["disposition"] == "ADJUST", line_b

    r_detail2 = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail2.status_code == 200, r_detail2.text
    detail2 = r_detail2.json()

    assert detail2["status"] == "COUNTED", detail2
    assert detail2["counted_at"], detail2


async def _post_load_lot_id_by_code(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str,
) -> int:
    row = await session.execute(
        text(
            """
            SELECT sl.lot_id
              FROM stocks_lot sl
              JOIN lots lo
                ON lo.id = sl.lot_id
             WHERE sl.warehouse_id = :warehouse_id
               AND sl.item_id = :item_id
               AND lo.lot_code = :lot_code
             ORDER BY sl.lot_id ASC
             LIMIT 1
            """
        ),
        {
            "warehouse_id": int(warehouse_id),
            "item_id": int(item_id),
            "lot_code": str(lot_code),
        },
    )
    lot_id = row.scalar_one_or_none()
    assert lot_id is not None, {"warehouse_id": warehouse_id, "item_id": item_id, "lot_code": lot_code}
    return int(lot_id)


async def _post_load_stock_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
) -> int:
    row = await session.execute(
        text(
            """
            SELECT qty
              FROM stocks_lot
             WHERE warehouse_id = :warehouse_id
               AND item_id = :item_id
               AND lot_id = :lot_id
             LIMIT 1
            """
        ),
        {
            "warehouse_id": int(warehouse_id),
            "item_id": int(item_id),
            "lot_id": int(lot_id),
        },
    )
    qty = row.scalar_one_or_none()
    return int(qty or 0)


async def _post_fetch_event(
    session: AsyncSession,
    *,
    event_id: int,
) -> dict[str, object]:
    row = await session.execute(
        text(
            """
            SELECT
              id,
              event_no,
              event_type,
              warehouse_id,
              source_type,
              source_ref,
              trace_id,
              event_kind,
              target_event_id,
              status,
              occurred_at
            FROM wms_events
            WHERE id = :event_id
            LIMIT 1
            """
        ),
        {"event_id": int(event_id)},
    )
    m = row.mappings().first()
    assert m is not None, {"event_id": event_id}
    return dict(m)


async def _post_fetch_ledgers(
    session: AsyncSession,
    *,
    event_id: int,
) -> list[dict[str, object]]:
    rows = await session.execute(
        text(
            """
            SELECT
              id,
              event_id,
              ref,
              ref_line,
              warehouse_id,
              item_id,
              lot_id,
              delta,
              after_qty,
              reason,
              reason_canon,
              sub_reason
            FROM stock_ledger
            WHERE event_id = :event_id
            ORDER BY id ASC
            """
        ),
        {"event_id": int(event_id)},
    )
    return [dict(x) for x in rows.mappings().all()]


@pytest.mark.asyncio
async def test_count_doc_post_zero_diff_marks_posted_and_writes_count_confirm(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_items_with_base_uom(session, limit=1)
    item = picked[0]

    batch_code = f"UT-CNT-POST-ZERO-{uuid4().hex[:8].upper()}"
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        batch_code=batch_code,
        qty=5,
        ref=f"ut:count-doc:post-zero-seed:{batch_code}",
    )
    await session.commit()

    created = await _create_count_doc(
        client,
        headers=headers,
        warehouse_id=warehouse_id,
        snapshot_at=datetime(2030, 1, 5, 8, 0, 0, tzinfo=UTC),
        remark="UT-COUNT-DOC-POST-ZERO",
    )
    doc_id = int(created["id"])

    r_freeze = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/freeze",
        headers=headers,
    )
    assert r_freeze.status_code == 200, r_freeze.text

    r_detail = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()
    assert detail["status"] == "FROZEN", detail
    assert len(detail["lines"]) == 1, detail

    line = detail["lines"][0]
    assert int(line["snapshot_qty_base"]) == 5, line
    assert len(line["lot_snapshots"]) == 1, line
    lot_id = int(line["lot_snapshots"][0]["lot_id"])

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "lines": [
                {
                    "line_id": int(line["id"]),
                    "counted_item_uom_id": int(item["item_uom_id"]),
                    "counted_qty_input": 5,
                    "reason_code": "MATCHED",
                    "disposition": "KEEP",
                    "remark": "ut post zero diff",
                }
            ]
        },
        headers=headers,
    )
    assert r_update.status_code == 200, r_update.text
    updated = r_update.json()
    assert updated["status"] == "COUNTED", updated

    r_post = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/post",
        headers=headers,
    )
    assert r_post.status_code == 200, r_post.text
    posted = r_post.json()

    assert int(posted["doc_id"]) == doc_id, posted
    assert posted["status"] == "POSTED", posted
    assert int(posted["posted_event_id"]) > 0, posted
    assert posted["posted_at"], posted

    r_detail2 = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail2.status_code == 200, r_detail2.text
    detail2 = r_detail2.json()
    assert detail2["status"] == "POSTED", detail2
    assert int(detail2["posted_event_id"]) == int(posted["posted_event_id"]), detail2
    assert _norm_utc_iso(detail2["posted_at"]) == _norm_utc_iso(posted["posted_at"]), detail2

    event = await _post_fetch_event(session, event_id=int(posted["posted_event_id"]))
    assert str(event["event_type"]) == "COUNT", event
    assert str(event["source_type"]) == "MANUAL_COUNT", event
    assert str(event["event_kind"]) == "COMMIT", event
    assert str(event["status"]) == "COMMITTED", event
    assert int(event["warehouse_id"]) == int(warehouse_id), event
    assert str(event["source_ref"]) == str(created["count_no"]), event

    ledgers = await _post_fetch_ledgers(session, event_id=int(posted["posted_event_id"]))
    assert len(ledgers) == 1, ledgers

    ledger = ledgers[0]
    assert str(ledger["sub_reason"]) == "COUNT_CONFIRM", ledger
    assert int(ledger["delta"]) == 0, ledger

    # 顶层 reason 以当前 stock_ledger 真相为准，不在这里写死为 COUNT；
    # 盘点语义由 sub_reason 稳定表达。
    assert str(ledger["reason_canon"]) in {"ADJUSTMENT", "COUNT"}, ledger
    assert int(ledger["warehouse_id"]) == int(warehouse_id), ledger
    assert int(ledger["item_id"]) == int(item["item_id"]), ledger
    assert int(ledger["lot_id"]) == int(lot_id), ledger

    qty_after = await _post_load_stock_qty(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        lot_id=int(lot_id),
    )
    assert qty_after == 5


@pytest.mark.asyncio
async def test_count_doc_post_negative_diff_splits_across_lot_snapshots(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_items_with_base_uom(session, limit=1)
    item = picked[0]

    code_small = f"UT-CNT-POST-SMALL-{uuid4().hex[:8].upper()}"
    code_big = f"UT-CNT-POST-BIG-{uuid4().hex[:8].upper()}"

    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        batch_code=code_small,
        qty=5,
        ref=f"ut:count-doc:post-split-seed:{code_small}",
        production_date=date(2030, 1, 1),
        expiry_date=date(2031, 1, 1),
    )
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        batch_code=code_big,
        qty=7,
        ref=f"ut:count-doc:post-split-seed:{code_big}",
        production_date=date(2030, 2, 1),
        expiry_date=date(2031, 2, 1),
    )
    await session.commit()

    created = await _create_count_doc(
        client,
        headers=headers,
        warehouse_id=warehouse_id,
        snapshot_at=datetime(2030, 1, 6, 8, 0, 0, tzinfo=UTC),
        remark="UT-COUNT-DOC-POST-SPLIT",
    )
    doc_id = int(created["id"])

    r_freeze = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/freeze",
        headers=headers,
    )
    assert r_freeze.status_code == 200, r_freeze.text

    r_detail = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()
    assert detail["status"] == "FROZEN", detail
    assert len(detail["lines"]) == 1, detail

    line = detail["lines"][0]
    assert int(line["snapshot_qty_base"]) == 12, line
    assert len(line["lot_snapshots"]) == 2, {"line": line, "msg": "expected exactly 2 lot snapshots for split-post test"}

    snapshots = sorted(
        line["lot_snapshots"],
        key=lambda x: (-int(x["snapshot_qty_base"]), int(x["lot_id"])),
    )
    assert int(snapshots[0]["snapshot_qty_base"]) == 7, snapshots
    assert int(snapshots[1]["snapshot_qty_base"]) == 5, snapshots

    lot_big = int(snapshots[0]["lot_id"])
    lot_small = int(snapshots[1]["lot_id"])

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "lines": [
                {
                    "line_id": int(line["id"]),
                    "counted_item_uom_id": int(item["item_uom_id"]),
                    "counted_qty_input": 4,
                    "reason_code": "LOSS",
                    "disposition": "ADJUST",
                    "remark": "ut post split diff",
                }
            ]
        },
        headers=headers,
    )
    assert r_update.status_code == 200, r_update.text
    updated = r_update.json()
    assert updated["status"] == "COUNTED", updated

    r_post = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/post",
        headers=headers,
    )
    assert r_post.status_code == 200, r_post.text
    posted = r_post.json()

    assert posted["status"] == "POSTED", posted
    event_id = int(posted["posted_event_id"])

    event = await _post_fetch_event(session, event_id=event_id)
    assert str(event["event_type"]) == "COUNT", event
    assert str(event["source_type"]) == "MANUAL_COUNT", event
    assert str(event["event_kind"]) == "COMMIT", event
    assert str(event["status"]) == "COMMITTED", event

    ledgers = await _post_fetch_ledgers(session, event_id=event_id)
    assert len(ledgers) == 2, ledgers
    assert all(str(x["sub_reason"]) == "COUNT_ADJUST" for x in ledgers), ledgers
    assert all(str(x["reason_canon"]) in {"ADJUSTMENT", "COUNT"} for x in ledgers), ledgers

    deltas = sorted(int(x["delta"]) for x in ledgers)
    assert deltas == [-7, -1], ledgers

    ledger_by_lot = {int(x["lot_id"]): x for x in ledgers}
    assert int(ledger_by_lot[lot_big]["delta"]) == -7, ledgers
    assert int(ledger_by_lot[lot_small]["delta"]) == -1, ledgers

    qty_big_after = await _post_load_stock_qty(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        lot_id=int(lot_big),
    )
    qty_small_after = await _post_load_stock_qty(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        lot_id=int(lot_small),
    )

    assert qty_big_after == 0
    assert qty_small_after == 4



@pytest.mark.asyncio
async def test_count_doc_post_zero_diff_three_books_consistent(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_items_with_base_uom(session, limit=1)
    item = picked[0]

    batch_code = f"UT-CNT-3BOOKS-ZERO-{uuid4().hex[:8].upper()}"
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        batch_code=batch_code,
        qty=5,
        ref=f"ut:count-doc:3books-zero-seed:{batch_code}",
    )
    await session.commit()

    created = await _create_count_doc(
        client,
        headers=headers,
        warehouse_id=warehouse_id,
        snapshot_at=datetime(2030, 1, 7, 8, 0, 0, tzinfo=UTC),
        remark="UT-COUNT-DOC-3BOOKS-ZERO",
    )
    doc_id = int(created["id"])

    r_freeze = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/freeze",
        headers=headers,
    )
    assert r_freeze.status_code == 200, r_freeze.text

    r_detail = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()
    assert detail["status"] == "FROZEN", detail
    assert len(detail["lines"]) == 1, detail

    line = detail["lines"][0]
    assert int(line["snapshot_qty_base"]) == 5, line

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "lines": [
                {
                    "line_id": int(line["id"]),
                    "counted_item_uom_id": int(item["item_uom_id"]),
                    "counted_qty_input": 5,
                    "reason_code": "MATCHED",
                    "disposition": "KEEP",
                    "remark": "ut 3books zero diff",
                }
            ]
        },
        headers=headers,
    )
    assert r_update.status_code == 200, r_update.text
    updated = r_update.json()
    assert updated["status"] == "COUNTED", updated

    r_post = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/post",
        headers=headers,
    )
    assert r_post.status_code == 200, r_post.text
    posted = r_post.json()
    assert posted["status"] == "POSTED", posted

    event = await _post_fetch_event(session, event_id=int(posted["posted_event_id"]))
    assert str(event["event_type"]) == "COUNT", event
    assert str(event["source_type"]) == "MANUAL_COUNT", event

    ledgers = await _post_fetch_ledgers(session, event_id=int(posted["posted_event_id"]))
    assert len(ledgers) == 1, ledgers
    assert str(ledgers[0]["sub_reason"]) == "COUNT_CONFIRM", ledgers
    assert int(ledgers[0]["delta"]) == 0, ledgers

    await run_snapshot(session)
    await verify_commit_three_books(
        session,
        warehouse_id=warehouse_id,
        ref=str(event["event_no"]),
        effects=[
            {
                "warehouse_id": warehouse_id,
                "item_id": int(item["item_id"]),
                "batch_code": batch_code,
                "qty": 0,
                "ref": str(event["event_no"]),
                "ref_line": 1,
            }
        ],
        at=event["occurred_at"],
    )


@pytest.mark.asyncio
async def test_count_doc_post_negative_diff_three_books_consistent(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_items_with_base_uom(session, limit=1)
    item = picked[0]

    code_small = f"UT-CNT-3BOOKS-SMALL-{uuid4().hex[:8].upper()}"
    code_big = f"UT-CNT-3BOOKS-BIG-{uuid4().hex[:8].upper()}"

    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        batch_code=code_small,
        qty=5,
        ref=f"ut:count-doc:3books-split-seed:{code_small}",
        production_date=date(2030, 1, 1),
        expiry_date=date(2031, 1, 1),
    )
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        batch_code=code_big,
        qty=7,
        ref=f"ut:count-doc:3books-split-seed:{code_big}",
        production_date=date(2030, 2, 1),
        expiry_date=date(2031, 2, 1),
    )
    await session.commit()

    created = await _create_count_doc(
        client,
        headers=headers,
        warehouse_id=warehouse_id,
        snapshot_at=datetime(2030, 1, 8, 8, 0, 0, tzinfo=UTC),
        remark="UT-COUNT-DOC-3BOOKS-SPLIT",
    )
    doc_id = int(created["id"])

    r_freeze = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/freeze",
        headers=headers,
    )
    assert r_freeze.status_code == 200, r_freeze.text

    r_detail = await client.get(f"/inventory-adjustment/count-docs/{doc_id}", headers=headers)
    assert r_detail.status_code == 200, r_detail.text
    detail = r_detail.json()
    assert detail["status"] == "FROZEN", detail
    assert len(detail["lines"]) == 1, detail

    line = detail["lines"][0]
    assert int(line["snapshot_qty_base"]) == 12, line
    assert len(line["lot_snapshots"]) == 2, line

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "lines": [
                {
                    "line_id": int(line["id"]),
                    "counted_item_uom_id": int(item["item_uom_id"]),
                    "counted_qty_input": 4,
                    "reason_code": "LOSS",
                    "disposition": "ADJUST",
                    "remark": "ut 3books split diff",
                }
            ]
        },
        headers=headers,
    )
    assert r_update.status_code == 200, r_update.text
    updated = r_update.json()
    assert updated["status"] == "COUNTED", updated

    r_post = await client.post(
        f"/inventory-adjustment/count-docs/{doc_id}/post",
        headers=headers,
    )
    assert r_post.status_code == 200, r_post.text
    posted = r_post.json()
    assert posted["status"] == "POSTED", posted

    event = await _post_fetch_event(session, event_id=int(posted["posted_event_id"]))
    assert str(event["event_type"]) == "COUNT", event
    assert str(event["source_type"]) == "MANUAL_COUNT", event

    ledgers = await _post_fetch_ledgers(session, event_id=int(posted["posted_event_id"]))
    assert len(ledgers) == 2, ledgers
    assert all(str(x["sub_reason"]) == "COUNT_ADJUST" for x in ledgers), ledgers

    deltas = sorted(int(x["delta"]) for x in ledgers)
    assert deltas == [-7, -1], ledgers

    await run_snapshot(session)
    await verify_commit_three_books(
        session,
        warehouse_id=warehouse_id,
        ref=str(event["event_no"]),
        effects=[
            {
                "warehouse_id": warehouse_id,
                "item_id": int(item["item_id"]),
                "batch_code": code_big,
                "qty": -7,
                "ref": str(event["event_no"]),
                "ref_line": 1,
            },
            {
                "warehouse_id": warehouse_id,
                "item_id": int(item["item_id"]),
                "batch_code": code_small,
                "qty": -1,
                "ref": str(event["event_no"]),
                "ref_line": 1,
            },
        ],
        at=event["occurred_at"],
    )
