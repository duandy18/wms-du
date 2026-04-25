from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.services.three_books_consistency import verify_commit_three_books
from app.wms.snapshot.services.snapshot_run import run_snapshot
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
                  AND COALESCE(u.is_base, false) = true
                ORDER BY i.id ASC, u.id ASC
                """
            )
        )
    ).mappings().all()

    items = [dict(x) for x in rows[:limit]]
    assert len(items) >= limit, f"need at least {limit} enabled items with base uom"
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
    _ = ref
    _ = production_date
    _ = expiry_date
    await set_stock_qty(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        batch_code=str(batch_code),
        qty=int(qty),
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


async def _fetch_execution_detail(
    client: httpx.AsyncClient,
    *,
    headers: dict[str, str],
    doc_id: int,
) -> dict[str, object]:
    resp = await client.get(
        f"/inventory-adjustment/count-docs/{doc_id}/execution",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _fetch_doc_line_lot_snapshots(
    session: AsyncSession,
    *,
    doc_id: int,
) -> list[dict[str, object]]:
    rows = await session.execute(
        text(
            """
            SELECT
              l.id AS line_id,
              l.line_no,
              l.item_id,
              s.lot_id,
              s.lot_code_snapshot,
              s.snapshot_qty_base
            FROM count_doc_lines l
            JOIN count_doc_line_lot_snapshots s
              ON s.line_id = l.id
            WHERE l.doc_id = :doc_id
            ORDER BY l.line_no ASC, s.snapshot_qty_base DESC, s.lot_id ASC
            """
        ),
        {"doc_id": int(doc_id)},
    )
    return [dict(x) for x in rows.mappings().all()]


async def _fetch_event(
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


async def _fetch_ledgers(
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


async def _load_stock_qty(
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


@pytest.mark.asyncio
async def test_count_doc_freeze_generates_item_lines_and_db_lot_snapshots(
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

    execution = await _fetch_execution_detail(client, headers=headers, doc_id=doc_id)
    assert execution["status"] == "FROZEN", execution
    assert len(execution["lines"]) >= 2, execution

    lines_by_item = {int(x["item_id"]): x for x in execution["lines"]}
    assert int(lines_by_item[int(item_a["item_id"])]["snapshot_qty_base"]) == 12, execution
    assert int(lines_by_item[int(item_b["item_id"])]["snapshot_qty_base"]) == 3, execution

    snapshots = await _fetch_doc_line_lot_snapshots(session, doc_id=doc_id)
    assert len(snapshots) == int(frozen["lot_snapshot_count"]), {
        "snapshots": snapshots,
        "frozen": frozen,
    }

    a_line_id = int(lines_by_item[int(item_a["item_id"])]["id"])
    b_line_id = int(lines_by_item[int(item_b["item_id"])]["id"])

    a_sum = sum(int(x["snapshot_qty_base"]) for x in snapshots if int(x["line_id"]) == a_line_id)
    b_sum = sum(int(x["snapshot_qty_base"]) for x in snapshots if int(x["line_id"]) == b_line_id)

    assert a_sum == 12, snapshots
    assert b_sum == 3, snapshots


@pytest.mark.asyncio
async def test_count_doc_update_lines_marks_counted_and_execution_detail_is_base_unit(
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> None:
    headers = await _login_admin_headers(client)
    warehouse_id = await _pick_active_warehouse_id(session)
    picked = await _pick_enabled_items_with_base_uom(session, limit=2)

    item_a = picked[0]
    item_b = picked[1]

    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item_a["item_id"]),
        batch_code=f"UT-CNT-UPD-A-{uuid4().hex[:8].upper()}",
        qty=4,
        ref="ut:count-doc:update-seed:a",
    )
    await _seed_positive_stock(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item_b["item_id"]),
        batch_code=f"UT-CNT-UPD-B-{uuid4().hex[:8].upper()}",
        qty=2,
        ref="ut:count-doc:update-seed:b",
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

    execution = await _fetch_execution_detail(client, headers=headers, doc_id=doc_id)

    payload_lines = []
    for line in execution["lines"]:
        item_id = int(line["item_id"])
        snapshot_qty_base = int(line["snapshot_qty_base"])
        counted_qty_input = snapshot_qty_base if item_id == int(item_a["item_id"]) else snapshot_qty_base - 1
        payload_lines.append({
            "line_id": int(line["id"]),
            "counted_qty_input": counted_qty_input,
        })

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "counted_by_name_snapshot": "张三",
            "lines": payload_lines,
        },
        headers=headers,
    )
    assert r_update.status_code == 200, r_update.text
    updated = r_update.json()
    assert updated["status"] == "COUNTED", updated

    execution2 = await _fetch_execution_detail(client, headers=headers, doc_id=doc_id)
    assert execution2["status"] == "COUNTED", execution2
    assert execution2["counted_by_name_snapshot"] == "张三", execution2
    assert execution2["reviewed_by_name_snapshot"] is None, execution2

    lines_by_item = {int(x["item_id"]): x for x in execution2["lines"]}

    line_a = lines_by_item[int(item_a["item_id"])]
    assert int(line_a["counted_qty_input"]) == int(line_a["snapshot_qty_base"]), line_a
    assert int(line_a["counted_qty_base"]) == int(line_a["snapshot_qty_base"]), line_a
    assert int(line_a["diff_qty_base"]) == 0, line_a
    assert line_a["base_uom_name"], line_a

    line_b = lines_by_item[int(item_b["item_id"])]
    assert int(line_b["counted_qty_input"]) == int(line_b["snapshot_qty_base"]) - 1, line_b
    assert int(line_b["counted_qty_base"]) == int(line_b["snapshot_qty_base"]) - 1, line_b
    assert int(line_b["diff_qty_base"]) == -1, line_b
    assert line_b["base_uom_name"], line_b


@pytest.mark.asyncio
async def test_count_doc_post_zero_diff_keeps_three_books_consistent(
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

    execution = await _fetch_execution_detail(client, headers=headers, doc_id=doc_id)
    assert len(execution["lines"]) >= 1, execution
    target_line = next(x for x in execution["lines"] if int(x["item_id"]) == int(item["item_id"]))

    snapshots = await _fetch_doc_line_lot_snapshots(session, doc_id=doc_id)
    target_snaps = [x for x in snapshots if int(x["line_id"]) == int(target_line["id"])]
    assert len(target_snaps) == 1, target_snaps
    lot_id = int(target_snaps[0]["lot_id"])

    update_lines = []
    for line in execution["lines"]:
        update_lines.append({
            "line_id": int(line["id"]),
            "counted_qty_input": int(line["snapshot_qty_base"]),
        })

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "counted_by_name_snapshot": "张三",
            "lines": update_lines,
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
    posted = r_post.json()

    event = await _fetch_event(session, event_id=int(posted["posted_event_id"]))
    assert str(event["event_type"]) == "COUNT", event
    assert str(event["source_type"]) == "MANUAL_COUNT", event
    assert str(event["event_kind"]) == "COMMIT", event
    assert str(event["status"]) == "COMMITTED", event

    ledgers = await _fetch_ledgers(session, event_id=int(posted["posted_event_id"]))
    target_ledgers = [x for x in ledgers if int(x["item_id"]) == int(item["item_id"])]
    assert len(target_ledgers) == 1, ledgers
    assert str(target_ledgers[0]["sub_reason"]) == "COUNT_CONFIRM", target_ledgers[0]
    assert int(target_ledgers[0]["delta"]) == 0, target_ledgers[0]

    qty_after = await _load_stock_qty(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        lot_id=lot_id,
    )
    assert qty_after == 5

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
                "ref_line": int(target_line["line_no"]),
            }
        ],
        at=event["occurred_at"],
    )


@pytest.mark.asyncio
async def test_count_doc_post_negative_diff_splits_by_db_lot_snapshots_and_keeps_three_books_consistent(
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

    execution = await _fetch_execution_detail(client, headers=headers, doc_id=doc_id)
    target_line = next(x for x in execution["lines"] if int(x["item_id"]) == int(item["item_id"]))

    snapshots = await _fetch_doc_line_lot_snapshots(session, doc_id=doc_id)
    target_snaps = [x for x in snapshots if int(x["line_id"]) == int(target_line["id"])]
    assert len(target_snaps) == 2, target_snaps

    target_snaps = sorted(
        target_snaps,
        key=lambda x: (-int(x["snapshot_qty_base"]), int(x["lot_id"])),
    )
    lot_big = int(target_snaps[0]["lot_id"])
    lot_small = int(target_snaps[1]["lot_id"])

    update_lines = []
    for line in execution["lines"]:
        counted_qty_input = 4 if int(line["item_id"]) == int(item["item_id"]) else int(line["snapshot_qty_base"])
        update_lines.append({
            "line_id": int(line["id"]),
            "counted_qty_input": counted_qty_input,
        })

    r_update = await client.put(
        f"/inventory-adjustment/count-docs/{doc_id}/lines",
        json={
            "counted_by_name_snapshot": "张三",
            "lines": update_lines,
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
    posted = r_post.json()

    event = await _fetch_event(session, event_id=int(posted["posted_event_id"]))
    assert str(event["event_type"]) == "COUNT", event
    assert str(event["source_type"]) == "MANUAL_COUNT", event
    assert str(event["event_kind"]) == "COMMIT", event
    assert str(event["status"]) == "COMMITTED", event

    ledgers = await _fetch_ledgers(session, event_id=int(posted["posted_event_id"]))
    target_ledgers = [x for x in ledgers if int(x["item_id"]) == int(item["item_id"])]
    assert len(target_ledgers) == 2, target_ledgers
    assert all(str(x["sub_reason"]) == "COUNT_ADJUST" for x in target_ledgers), target_ledgers

    deltas = sorted(int(x["delta"]) for x in target_ledgers)
    assert deltas == [-7, -1], target_ledgers

    ledger_by_lot = {int(x["lot_id"]): x for x in target_ledgers}
    assert int(ledger_by_lot[lot_big]["delta"]) == -7, target_ledgers
    assert int(ledger_by_lot[lot_small]["delta"]) == -1, target_ledgers

    qty_big_after = await _load_stock_qty(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        lot_id=lot_big,
    )
    qty_small_after = await _load_stock_qty(
        session,
        warehouse_id=warehouse_id,
        item_id=int(item["item_id"]),
        lot_id=lot_small,
    )

    assert qty_big_after == 0
    assert qty_small_after == 4

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
                "ref_line": int(target_line["line_no"]),
            },
            {
                "warehouse_id": warehouse_id,
                "item_id": int(item["item_id"]),
                "batch_code": code_small,
                "qty": -1,
                "ref": str(event["event_no"]),
                "ref_line": int(target_line["line_no"]),
            },
        ],
        at=event["occurred_at"],
    )
