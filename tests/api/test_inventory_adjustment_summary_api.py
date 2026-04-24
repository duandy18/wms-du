from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


REQUIRED_ROW_KEYS = {
    "adjustment_type",
    "object_id",
    "object_no",
    "warehouse_id",
    "status",
    "source_type",
    "source_ref",
    "event_type",
    "event_kind",
    "target_event_id",
    "occurred_at",
    "committed_at",
    "created_at",
    "line_count",
    "qty_total",
    "ledger_row_count",
    "ledger_reason",
    "ledger_reason_canon",
    "ledger_sub_reason",
    "delta_total",
    "abs_delta_total",
    "direction",
    "action_title",
    "action_summary",
    "remark",
    "detail_route",
}


async def _scalar_required(session: AsyncSession, sql: str) -> int:
    value = (await session.execute(text(sql))).scalar_one_or_none()
    assert value is not None, sql
    return int(value)


async def _seed_count_summary_row(session: AsyncSession) -> dict[str, int | str]:
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:8].upper()

    warehouse_id = await _scalar_required(
        session,
        "SELECT id FROM warehouses ORDER BY id ASC LIMIT 1",
    )
    item_id = await _scalar_required(
        session,
        "SELECT id FROM items ORDER BY id ASC LIMIT 1",
    )

    lot_id = (
        await session.execute(
            text(
                """
                SELECT id
                FROM lots
                WHERE warehouse_id = :warehouse_id
                  AND item_id = :item_id
                ORDER BY id ASC
                LIMIT 1
                """
            ),
            {
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
            },
        )
    ).scalar_one_or_none()

    if lot_id is None:
        lot_id = (
            await session.execute(
                text(
                    """
                    INSERT INTO lots (
                      warehouse_id,
                      item_id,
                      lot_code_source,
                      lot_code,
                      source_receipt_id,
                      source_line_no,
                      created_at,
                      item_shelf_life_value_snapshot,
                      item_shelf_life_unit_snapshot,
                      item_lot_source_policy_snapshot,
                      item_expiry_policy_snapshot,
                      item_derivation_allowed_snapshot,
                      item_uom_governance_enabled_snapshot,
                      production_date,
                      expiry_date
                    )
                    VALUES (
                      :warehouse_id,
                      :item_id,
                      'INTERNAL',
                      NULL,
                      NULL,
                      NULL,
                      :created_at,
                      NULL,
                      NULL,
                      'INTERNAL_ONLY',
                      'NONE',
                      FALSE,
                      FALSE,
                      NULL,
                      NULL
                    )
                    RETURNING id
                    """
                ),
                {
                    "warehouse_id": int(warehouse_id),
                    "item_id": int(item_id),
                    "created_at": now,
                },
            )
        ).scalar_one()

    base_uom = (
        await session.execute(
            text(
                """
                SELECT
                  id,
                  COALESCE(NULLIF(display_name, ''), uom) AS uom_name
                FROM item_uoms
                WHERE item_id = :item_id
                  AND is_base IS TRUE
                ORDER BY id ASC
                LIMIT 1
                """
            ),
            {"item_id": int(item_id)},
        )
    ).mappings().first()
    assert base_uom is not None, f"base item_uom not found for item_id={item_id}"

    item_row = (
        await session.execute(
            text(
                """
                SELECT
                  name,
                  spec
                FROM items
                WHERE id = :item_id
                LIMIT 1
                """
            ),
            {"item_id": int(item_id)},
        )
    ).mappings().one()

    count_no = f"CTD-SUMMARY-UT-{suffix}"
    event_no = f"CNT-SUMMARY-UT-{suffix}"
    trace_id = f"COUNT-SUMMARY-UT-{suffix}"

    event_id = int(
        (
            await session.execute(
                text(
                    """
                    INSERT INTO wms_events (
                      event_no,
                      event_type,
                      warehouse_id,
                      source_type,
                      source_ref,
                      occurred_at,
                      committed_at,
                      trace_id,
                      event_kind,
                      target_event_id,
                      status,
                      created_by,
                      remark,
                      created_at
                    )
                    VALUES (
                      :event_no,
                      'COUNT',
                      :warehouse_id,
                      'MANUAL_COUNT',
                      :source_ref,
                      :occurred_at,
                      :committed_at,
                      :trace_id,
                      'COMMIT',
                      NULL,
                      'COMMITTED',
                      NULL,
                      :remark,
                      :created_at
                    )
                    RETURNING id
                    """
                ),
                {
                    "event_no": event_no,
                    "warehouse_id": warehouse_id,
                    "source_ref": count_no,
                    "occurred_at": now,
                    "committed_at": now,
                    "trace_id": trace_id,
                    "remark": "UT inventory adjustment summary detail",
                    "created_at": now,
                },
            )
        ).scalar_one()
    )

    doc_id = int(
        (
            await session.execute(
                text(
                    """
                    INSERT INTO count_docs (
                      count_no,
                      warehouse_id,
                      snapshot_at,
                      status,
                      posted_event_id,
                      created_by,
                      remark,
                      created_at,
                      counted_at,
                      posted_at,
                      counted_by_name_snapshot,
                      reviewed_by_name_snapshot
                    )
                    VALUES (
                      :count_no,
                      :warehouse_id,
                      :snapshot_at,
                      'POSTED',
                      :posted_event_id,
                      NULL,
                      :remark,
                      :created_at,
                      :counted_at,
                      :posted_at,
                      :counted_by_name_snapshot,
                      :reviewed_by_name_snapshot
                    )
                    RETURNING id
                    """
                ),
                {
                    "count_no": count_no,
                    "warehouse_id": warehouse_id,
                    "snapshot_at": now,
                    "posted_event_id": event_id,
                    "remark": "UT inventory adjustment summary detail",
                    "created_at": now,
                    "counted_at": now,
                    "posted_at": now,
                    "counted_by_name_snapshot": "UT盘点人",
                    "reviewed_by_name_snapshot": "UT复核人",
                },
            )
        ).scalar_one()
    )

    await session.execute(
        text(
            """
            INSERT INTO count_doc_lines (
              doc_id,
              line_no,
              item_id,
              item_name_snapshot,
              item_spec_snapshot,
              snapshot_qty_base,
              counted_item_uom_id,
              counted_uom_name_snapshot,
              counted_ratio_to_base_snapshot,
              counted_qty_input,
              counted_qty_base,
              diff_qty_base,
              created_at,
              updated_at
            )
            VALUES (
              :doc_id,
              1,
              :item_id,
              :item_name_snapshot,
              :item_spec_snapshot,
              10,
              :counted_item_uom_id,
              :counted_uom_name_snapshot,
              1,
              10,
              10,
              0,
              :created_at,
              :updated_at
            )
            """
        ),
        {
            "doc_id": doc_id,
            "item_id": item_id,
            "item_name_snapshot": item_row["name"],
            "item_spec_snapshot": item_row["spec"],
            "counted_item_uom_id": int(base_uom["id"]),
            "counted_uom_name_snapshot": str(base_uom["uom_name"]),
            "created_at": now,
            "updated_at": now,
        },
    )

    await session.execute(
        text(
            """
            INSERT INTO stock_ledger (
              reason,
              after_qty,
              delta,
              occurred_at,
              ref,
              ref_line,
              item_id,
              created_at,
              warehouse_id,
              trace_id,
              production_date,
              expiry_date,
              sub_reason,
              reason_canon,
              lot_id,
              event_id
            )
            VALUES (
              'ADJUSTMENT',
              10,
              0,
              :occurred_at,
              :ref,
              1,
              :item_id,
              :created_at,
              :warehouse_id,
              :trace_id,
              NULL,
              NULL,
              'COUNT_CONFIRM',
              'ADJUSTMENT',
              :lot_id,
              :event_id
            )
            """
        ),
        {
            "occurred_at": now,
            "ref": event_no,
            "item_id": item_id,
            "created_at": now,
            "warehouse_id": warehouse_id,
            "trace_id": trace_id,
            "lot_id": int(lot_id) if lot_id is not None else None,
            "event_id": event_id,
        },
    )

    return {
        "doc_id": doc_id,
        "event_id": event_id,
        "count_no": count_no,
        "event_no": event_no,
        "item_id": item_id,
        "warehouse_id": warehouse_id,
    }


@pytest.mark.asyncio
async def test_inventory_adjustment_summary_contract_returns_list(client):
    resp = await client.get("/inventory-adjustment/summary?limit=20&offset=0")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int)
    assert body["limit"] == 20
    assert body["offset"] == 0

    for row in body["items"]:
        assert REQUIRED_ROW_KEYS.issubset(row.keys()), row
        assert row["adjustment_type"] in {
            "COUNT",
            "INBOUND_REVERSAL",
            "OUTBOUND_REVERSAL",
        }
        assert isinstance(row["object_id"], int)
        assert isinstance(row["object_no"], str)
        assert isinstance(row["warehouse_id"], int)
        assert isinstance(row["line_count"], int)
        assert isinstance(row["qty_total"], int)
        assert isinstance(row["ledger_row_count"], int)
        assert isinstance(row["delta_total"], int)
        assert isinstance(row["abs_delta_total"], int)
        assert isinstance(row["direction"], str)
        assert row["direction"] in {"INCREASE", "DECREASE", "CONFIRM", "PENDING"}
        assert isinstance(row["action_title"], str)
        assert row["action_title"].strip()
        assert isinstance(row["action_summary"], str)
        assert row["action_summary"].strip()
        assert isinstance(row["detail_route"], str)
        assert row["detail_route"].startswith("/inventory-adjustment/")


@pytest.mark.asyncio
async def test_inventory_adjustment_summary_detail_returns_ledger_rows(
    client,
    session: AsyncSession,
):
    seeded = await _seed_count_summary_row(session)
    await session.commit()

    resp = await client.get("/inventory-adjustment/summary?adjustment_type=COUNT&limit=20&offset=0")
    assert resp.status_code == 200, resp.text

    items = resp.json()["items"]
    target = next(
        item for item in items
        if item["adjustment_type"] == "COUNT"
        and int(item["object_id"]) == int(seeded["doc_id"])
    )

    assert target["object_no"] == seeded["count_no"]
    assert target["ledger_sub_reason"] == "COUNT_CONFIRM"
    assert target["delta_total"] == 0
    assert target["action_summary"] == "盘点确认，无差异"

    detail_resp = await client.get(
        f"/inventory-adjustment/summary/{target['adjustment_type']}/{target['object_id']}"
    )
    assert detail_resp.status_code == 200, detail_resp.text

    body = detail_resp.json()
    assert set(body.keys()) == {"row", "ledger_rows"}
    assert body["row"]["adjustment_type"] == "COUNT"
    assert int(body["row"]["object_id"]) == int(seeded["doc_id"])

    ledger_rows = body["ledger_rows"]
    assert len(ledger_rows) == 1

    ledger = ledger_rows[0]
    assert int(ledger["event_id"]) == int(seeded["event_id"])
    assert int(ledger["warehouse_id"]) == int(seeded["warehouse_id"])
    assert int(ledger["item_id"]) == int(seeded["item_id"])
    assert ledger["item_name"]
    assert ledger["base_uom_name"]
    assert ledger["sub_reason"] == "COUNT_CONFIRM"
    assert ledger["reason_canon"] == "ADJUSTMENT"
    assert int(ledger["delta"]) == 0
    assert int(ledger["after_qty"]) == 10
    assert ledger["trace_id"] == seeded["event_no"].replace("CNT-SUMMARY-UT-", "COUNT-SUMMARY-UT-")
